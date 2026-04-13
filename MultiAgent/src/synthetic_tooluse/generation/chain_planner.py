"""
Intent-aware chain planning: domain filtering, semantic scoring, template chains,
and graph fallback when templates are unavailable.
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx

from synthetic_tooluse.schemas.graph import (
    ChainConstraints,
    ChainPattern,
    ChainPlan,
    ChainStep,
    RelationType,
)
from synthetic_tooluse.schemas.registry import EndpointDescriptor, ToolDefinition

logger = logging.getLogger(__name__)

# intent_name -> candidate endpoint sequences (ordered workflows).
PREDEFINED_CHAINS: Dict[str, List[List[str]]] = {
    "trip planning": [
        [
            "Travel/flights_api/search_flights",
            "Travel/hotels_api/search_hotels",
            "Travel/hotels_api/book_hotel",
        ],
        [
            "Travel/flights_api/search_flights",
            "Travel/hotels_api/search_hotels",
            "Travel/itinerary_api/get_attractions",
            "Travel/itinerary_api/plan_itinerary",
        ],
        [
            "Travel/hotels_api/search_hotels",
            "Travel/itinerary_api/get_attractions",
            "Travel/flights_api/search_flights",
            "Travel/itinerary_api/plan_itinerary",
        ],
    ],
    "budgeting and finance": [
        [
            "Finance/budget_api/calculate_budget",
            "Finance/expense_api/track_expenses",
            "Finance/savings_api/savings_planner",
        ],
    ],
    "savings and cash flow": [
        [
            "Finance/budget_api/calculate_budget",
            "Finance/expense_api/track_expenses",
            "Finance/savings_api/savings_planner",
        ],
    ],
    "schedule and productivity": [
        [
            "Productivity/schedule_api/create_schedule",
            "Productivity/reminder_api/set_reminder",
            "Productivity/calendar_api/add_calendar_event",
        ],
    ],
    "account management": [
        [
            "Account/profile_api/get_account_info",
            "Account/billing_api/list_payment_methods",
            "Account/billing_api/update_payment_method",
        ],
    ],
    "research and information": [
        [
            "Knowledge/articles_api/search_articles",
            "Knowledge/summarizer_api/summarize_content",
            "Knowledge/articles_api/search_articles",
        ],
    ],
}


def _keyword_score(node_data: dict, keywords: Sequence[str]) -> float:
    if not keywords:
        return 0.0
    text = f"{node_data.get('description', '')} {node_data.get('endpoint_id', '')}".lower()
    return float(sum(1 for k in keywords if k.lower() in text))


def _collect_candidate_nodes(
    graph: nx.DiGraph,
    domains: Set[str],
    constraints: ChainConstraints,
) -> List[Tuple[str, dict]]:
    """Filter graph nodes by domain and negative keywords; score with positive keywords."""
    out: List[Tuple[str, dict, float]] = []
    neg = [n.lower() for n in (constraints.negative_keywords or [])]
    pos = [p.lower() for p in (constraints.positive_keywords or [])]

    for n, d in graph.nodes(data=True):
        if not isinstance(n, str):
            continue
        dom = str(d.get("domain", ""))
        if domains and dom not in domains:
            continue
        desc_dom = f"{d.get('description', '')} {dom}".lower()
        if any(bad in desc_dom or bad in str(d.get("endpoint_id", "")).lower() for bad in neg):
            continue
        score = _keyword_score(d, pos)
        out.append((n, d, score))

    out.sort(key=lambda x: x[2], reverse=True)
    if not out:
        return []

    # Keep top semantic matches; if that removes everything (pos keywords empty), keep all filtered.
    if pos:
        max_score = out[0][2]
        threshold = max_score if max_score <= 0 else max(0.0, max_score - 1.0)
        relaxed = [(n, d) for n, d, s in out if s >= threshold]
        if relaxed:
            logger.debug(
                "chain_planner: semantic filter kept %d/%d nodes (threshold=%.1f)",
                len(relaxed),
                len(out),
                threshold,
            )
            return relaxed

    return [(n, d) for n, d, _ in out]


def _collect_candidate_nodes_lenient(
    graph: nx.DiGraph,
    domains: Set[str],
    constraints: ChainConstraints,
) -> List[Tuple[str, dict]]:
    """Same as _collect_candidate_nodes but drops negative-keyword filtering if nothing survives."""
    primary = _collect_candidate_nodes(graph, domains, constraints)
    if primary:
        return primary
    logger.warning("chain_planner: no nodes after keyword/domain filter; retrying without negative keywords")
    relaxed = constraints.model_copy(update={"negative_keywords": []})
    return _collect_candidate_nodes(graph, domains, relaxed)


def _pick_weighted_successor(
    graph: nx.DiGraph,
    curr: str,
    path: List[str],
    allowed: Set[str],
    curr_tool: str,
    prefer_distinct_tool: bool,
) -> Optional[str]:
    neighbors = [n for n in graph.successors(curr) if n in allowed and n not in path]
    if not neighbors:
        return None

    scored: List[Tuple[str, float]] = []
    for n in neighbors:
        data = graph.get_edge_data(curr, n) or {}
        props = data.get("properties") or []
        w = 0.5
        for p in props:
            rel = p.get("relation_type")
            wt = float(p.get("weight", 1.0))
            rel_name = getattr(rel, "value", rel)
            if rel_name in (RelationType.OUTPUT_TO_INPUT_COMPATIBLE.value, RelationType.OUTPUT_TO_INPUT_COMPATIBLE):
                w += 3.0 * wt
            elif rel_name in (RelationType.SAME_DOMAIN.value, RelationType.SAME_DOMAIN):
                w += 1.0 * wt
            elif rel_name in (RelationType.SAME_TOOL.value, RelationType.SAME_TOOL):
                w += 0.2 * wt
        n_tool = graph.nodes[n].get("tool_id")
        if prefer_distinct_tool and n_tool and n_tool != curr_tool:
            w += 2.0
        scored.append((n, w))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = [n for n, s in scored if s >= scored[0][1] - 0.25]
    return random.choice(top)


def _graph_random_walk(
    graph: nx.DiGraph,
    allowed_nodes: Set[str],
    num_steps: int,
    constraints: ChainConstraints,
) -> List[str]:
    nodes_list = [n for n in allowed_nodes if n in graph]
    if not nodes_list:
        return []

    scored_starts = sorted(
        nodes_list,
        key=lambda nid: _keyword_score(graph.nodes[nid], constraints.positive_keywords or []),
        reverse=True,
    )
    pool = scored_starts[: max(1, min(8, len(scored_starts)))]
    start = random.choice(pool)
    path = [start]

    for _ in range(num_steps - 1):
        curr = path[-1]
        curr_tool = graph.nodes[curr].get("tool_id")
        nxt = _pick_weighted_successor(
            graph,
            curr,
            path,
            allowed_nodes,
            curr_tool,
            prefer_distinct_tool=bool(constraints.require_multi_tool),
        )
        if not nxt:
            break
        path.append(nxt)
    return path


def _resolve_domains(constraints: ChainConstraints) -> Set[str]:
    if constraints.required_domains:
        return {str(d) for d in constraints.required_domains}
    return set()


def _predefined_path(
    intent_name: Optional[str],
    endpoints: Dict[str, EndpointDescriptor],
) -> Optional[List[str]]:
    """Longest registered template chain for the intent (avoids accidental 1-step plans)."""
    if not intent_name:
        return None
    key = intent_name.strip().lower()
    candidates = PREDEFINED_CHAINS.get(key)
    if not candidates:
        return None
    valid = [list(c) for c in candidates if all(ep in endpoints for ep in c)]
    if not valid:
        return None
    return max(valid, key=len)


def _endpoint_ids_for_domains(registry: Dict[str, ToolDefinition], domains: Set[str]) -> Set[str]:
    if not domains:
        return set()
    out: Set[str] = set()
    for t in registry.values():
        if str(t.domain) not in domains:
            continue
        for e in t.endpoints:
            out.add(e.endpoint_id)
    return out


def _distinct_tool_count(steps: List[ChainStep], graph: nx.DiGraph) -> int:
    tids: Set[str] = set()
    for s in steps:
        tid = graph.nodes.get(s.endpoint_id, {}).get("tool_id")
        if tid:
            tids.add(tid)
    return len(tids)


def _steps_from_path(
    path: List[str],
    endpoints: Dict[str, EndpointDescriptor],
    graph: nx.DiGraph,
    registry: Dict[str, ToolDefinition],
    intent_label: str,
    constraints: ChainConstraints,
) -> Tuple[List[ChainStep], Set[str]]:
    steps: List[ChainStep] = []
    domains_used: Set[str] = set()
    filtered = [ep for ep in path if ep in endpoints]
    for idx, ep_id in enumerate(filtered):
        ep_def = endpoints[ep_id]
        node = graph.nodes.get(ep_id, {})
        req_slots = [p.name for p in ep_def.input_parameters if p.required]
        tid = node.get("tool_id")
        tdef = registry.get(tid) if tid else None
        dom = str(
            node.get("domain")
            or (tdef.domain if tdef else (ep_id.split("/")[0] if "/" in ep_id else "general"))
        )
        domains_used.add(dom)
        needs_clarification = bool(constraints.require_disambiguation and idx == 0 and random.random() < 0.35)
        steps.append(
            ChainStep(
                step_index=len(steps),
                endpoint_id=ep_id,
                purpose=f"Execute {ep_def.endpoint_name} for {intent_label or 'workflow'}",
                required_slots=req_slots,
                likely_needs_clarification=needs_clarification,
            )
        )
    return steps, domains_used


def build_chain_plan(
    graph: nx.DiGraph,
    registry: Dict[str, ToolDefinition],
    endpoints: Dict[str, EndpointDescriptor],
    constraints: ChainConstraints,
) -> ChainPlan:
    """
    Build a ChainPlan: prefer template chains for the intent, else semantic-filtered graph walk.
    """
    domains = _resolve_domains(constraints)
    intent_label = (constraints.intent_name or "").strip()
    workflow_template = constraints.workflow_template

    path: List[str] = []
    source = "template"

    predefined = _predefined_path(intent_label, endpoints)
    if predefined:
        path = list(predefined)
    else:
        source = "graph"
        candidates = _collect_candidate_nodes_lenient(graph, domains, constraints)
        allowed = {n for n, _ in candidates}

        if not allowed and domains:
            reg_eps = _endpoint_ids_for_domains(registry, domains)
            allowed = {n for n in reg_eps if n in graph.nodes}

        if not allowed and not domains:
            candidates = _collect_candidate_nodes_lenient(graph, set(), constraints)
            allowed = {n for n, _ in candidates}

        if not allowed and domains:
            allowed = {
                n
                for n, d in graph.nodes(data=True)
                if isinstance(n, str) and str(d.get("domain", "")) in domains
            }

        if not allowed:
            logger.warning("chain_planner: using full graph as last-resort node pool")
            allowed = {n for n in graph.nodes if isinstance(n, str)}

        max_s = len(allowed)

        def _pick_num_steps(lo: int, hi: int) -> int:
            a = max(1, min(lo, max_s))
            b = max(1, min(hi, max_s))
            if a > b:
                return max_s
            return random.randint(a, b)

        if constraints.exact_num_steps is not None:
            num_steps = max(1, min(constraints.exact_num_steps, max_s))
        elif constraints.require_multi_tool:
            num_steps = _pick_num_steps(3, 4)
        elif random.random() < 0.55:
            num_steps = _pick_num_steps(3, 4)
        else:
            num_steps = _pick_num_steps(2, 3)

        num_steps = max(1, min(num_steps, max_s))
        path = _graph_random_walk(graph, allowed, num_steps, constraints)

    steps, domains_used = _steps_from_path(path, endpoints, graph, registry, intent_label, constraints)

    if constraints.require_multi_tool:
        if len(steps) < 3 or _distinct_tool_count(steps, graph) < 2:
            alt = _predefined_path(intent_label, endpoints)
            alt_tools = {
                graph.nodes[e].get("tool_id")
                for e in (alt or [])
                if e in graph.nodes and graph.nodes[e].get("tool_id")
            }
            if alt and len(alt) >= 3 and len(alt_tools) >= 2:
                logger.info("chain_planner: upgrading plan to satisfy multi-tool pacing: %s", alt)
                path = list(alt)
                steps, domains_used = _steps_from_path(path, endpoints, graph, registry, intent_label, constraints)

    if not steps:
        any_ep = next(iter(endpoints.keys()))
        ep_def = endpoints[any_ep]
        steps = [
            ChainStep(
                step_index=0,
                endpoint_id=any_ep,
                purpose=f"Execute {ep_def.endpoint_name}",
                required_slots=[p.name for p in ep_def.input_parameters if p.required],
                likely_needs_clarification=False,
            )
        ]
        domains_used = {graph.nodes[any_ep].get("domain", "general")}

    logger.info(
        "chain_planner: intent=%r domain=%s source=%s steps=%s template=%r",
        intent_label,
        sorted(domains_used),
        source,
        [s.endpoint_id for s in steps],
        workflow_template,
    )

    return ChainPlan(
        chain_id=f"chain_{uuid.uuid4().hex[:8]}",
        target_domains=sorted(domains_used),
        intent_name=constraints.intent_name,
        intent_desc=constraints.intent_desc,
        workflow_template=workflow_template,
        steps=steps,
        global_pattern=ChainPattern.SEQUENTIAL,
        expected_final_task=f"Complete workflow for {intent_label or 'user request'}",
    )
