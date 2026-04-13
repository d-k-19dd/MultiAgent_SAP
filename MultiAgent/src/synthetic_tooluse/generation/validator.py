import ast
from typing import List, Optional, Set

from synthetic_tooluse.schemas.conversation import ConversationRecord
from synthetic_tooluse.schemas.evaluation import ValidationFailure, ValidationResult
from synthetic_tooluse.execution.state import SessionState
from synthetic_tooluse.schemas.graph import ChainPlan
from synthetic_tooluse.schemas.registry import ToolDefinition
from synthetic_tooluse.generation.execution_dedupe import stable_tool_signature
from synthetic_tooluse.generation.endpoint_audit import (
    audit_tool_call,
    summarize_order_violations,
)
from synthetic_tooluse.evaluation.trace_analyzer import (
    extraneous_tools_after_final_answer,
    has_repeated_workflow_segment,
)


def _known_ids_from_record_and_session(record: ConversationRecord, session: SessionState) -> Set[str]:
    known: Set[str] = set()
    for ent_map in session.entity_store.entities.values():
        for k in ent_map.keys():
            known.add(str(k))
    for msg in record.messages:
        if msg.role != "tool" or not msg.content:
            continue
        try:
            data = ast.literal_eval(msg.content)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if "id" not in str(k).lower():
                continue
            if isinstance(v, (str, int, float)):
                known.add(str(v))
    return known


def _tool_domain_for_endpoint(ep: str, registry: Optional[List[ToolDefinition]]) -> Optional[str]:
    if not registry:
        return None
    for t in registry:
        for e in t.endpoints:
            if e.endpoint_id == ep:
                return t.domain
    return None


_RESTART_PHRASES = (
    "start over",
    "from scratch",
    "begin again",
    "go back to the beginning",
    "let's restart",
    "lets restart",
    "start from the beginning",
)


class TraceValidator:
    """Validates trace constraints: tool usage, domain alignment, grounding, and chain strength."""

    def validate(
        self,
        record: ConversationRecord,
        session: SessionState,
        plan: ChainPlan,
        registry: Optional[List[ToolDefinition]] = None,
    ) -> ValidationResult:
        failures: List[ValidationFailure] = []

        num_calls = record.metadata.get("num_tool_calls", 0)
        distinct = record.metadata.get("num_distinct_tools", 0)
        endpoints_used: List[str] = list(record.metadata.get("endpoints_used", []))
        planned: Set[str] = {s.endpoint_id for s in plan.steps}
        allowed_domains: Set[str] = set(plan.target_domains or [])

        if num_calls == 0:
            failures.append(
                ValidationFailure(
                    tag="zero_tool_calls",
                    description="The conversation generated 0 tool calls.",
                    step_index=-1,
                )
            )

        # Duplicate identical (endpoint, args) in transcript
        seen_signatures: Set[str] = set()
        for step_idx, msg in enumerate(record.messages):
            if msg.role != "assistant" or not msg.tool_calls:
                continue
            for call in msg.tool_calls:
                sig = stable_tool_signature(call.endpoint, call.arguments)
                if sig in seen_signatures:
                    failures.append(
                        ValidationFailure(
                            tag="duplicate_tool_call",
                            description=f"Repeated identical tool call: {call.endpoint} with same arguments.",
                            step_index=step_idx,
                        )
                    )
                else:
                    seen_signatures.add(sig)

        if has_repeated_workflow_segment(endpoints_used):
            failures.append(
                ValidationFailure(
                    tag="repeated_workflow_block",
                    description="Endpoint sequence repeats a prior segment (workflow restarted mid-trace).",
                    step_index=-1,
                )
            )

        if extraneous_tools_after_final_answer(record):
            failures.append(
                ValidationFailure(
                    tag="extraneous_tool_after_completion",
                    description="Assistant issued tool calls after a substantial final answer.",
                    step_index=-1,
                )
            )

        tool_msg_count = sum(1 for m in record.messages if m.role == "tool")
        for msg in record.messages:
            if msg.role != "assistant" or not (msg.content or "").strip():
                continue
            low = msg.content.lower()
            if tool_msg_count >= 2 and any(p in low for p in _RESTART_PHRASES):
                failures.append(
                    ValidationFailure(
                        tag="task_restart_after_tools",
                        description="Assistant language suggests restarting the task after tool progress.",
                        step_index=-1,
                    )
                )
                break

        intent_key = (plan.intent_name or "").strip().lower()
        for v in summarize_order_violations(endpoints_used, intent_key):
            failures.append(
                ValidationFailure(
                    tag="weak_endpoint_order",
                    description=v,
                    step_index=-1,
                )
            )

        for ep in endpoints_used:
            ep_lower = str(ep).lower()
            tool_dom = _tool_domain_for_endpoint(str(ep), registry)
            if allowed_domains and tool_dom and tool_dom not in allowed_domains:
                failures.append(
                    ValidationFailure(
                        tag="domain_mismatch",
                        description=(
                            f"Endpoint {ep} (tool domain {tool_dom}) is outside planned domains "
                            f"{sorted(allowed_domains)}."
                        ),
                        step_index=-1,
                    )
                )

            if planned and ep not in planned:
                failures.append(
                    ValidationFailure(
                        tag="irrelevant_tool",
                        description=f"Endpoint {ep} was not part of the sampled chain plan.",
                        step_index=-1,
                    )
                )

            from synthetic_tooluse.generation.intents import INTENT_CONFIGS

            neg_keys: List[str] = []
            if plan.intent_name:
                for ic in INTENT_CONFIGS:
                    if ic.name == plan.intent_name:
                        neg_keys = ic.negative_keywords
                        break
            for negative in neg_keys:
                if negative in ep_lower:
                    failures.append(
                        ValidationFailure(
                            tag="irrelevant_tool_usage",
                            description=(
                                f"Endpoint {ep} conflicts with negative keyword '{negative}' "
                                f"for intent {plan.intent_name}."
                            ),
                            step_index=-1,
                        )
                    )
                    break

        for step_idx, msg in enumerate(record.messages):
            if msg.role != "assistant" or not msg.tool_calls:
                continue
            for call in msg.tool_calls:
                for line in audit_tool_call(call.endpoint, call.arguments, plan.intent_name, registry):
                    failures.append(
                        ValidationFailure(
                            tag="endpoint_argument_mismatch",
                            description=line,
                            step_index=step_idx,
                        )
                    )

        if distinct < 1:
            failures.append(
                ValidationFailure(
                    tag="low_diversity",
                    description="The conversation must use at least 1 distinct tool.",
                    step_index=-1,
                )
            )

        intended_multi = record.metadata.get("intended_multi_tool", False)
        if intended_multi and (num_calls < 3 or distinct < 2):
            failures.append(
                ValidationFailure(
                    tag="insufficient_tool_complexity",
                    description=(
                        f"Generated {num_calls} calls and {distinct} distinct tools, "
                        "but pacing required >= 3 calls and >= 2 distinct tools."
                    ),
                    step_index=-1,
                )
            )

        if len(plan.steps) >= 3 and num_calls < 3:
            failures.append(
                ValidationFailure(
                    tag="weak_chain",
                    description=f"Plan had {len(plan.steps)} steps but only {num_calls} tool calls executed.",
                    step_index=-1,
                )
            )

        has_assistant_after_tools = False
        seen_tool = False
        for msg in record.messages:
            if msg.role == "tool":
                seen_tool = True
            elif seen_tool and msg.role == "assistant" and (msg.content or "").strip():
                has_assistant_after_tools = True
        if num_calls > 0 and not has_assistant_after_tools:
            failures.append(
                ValidationFailure(
                    tag="no_task_completion",
                    description="No final assistant message after tool results.",
                    step_index=-1,
                )
            )

        known_ids = _known_ids_from_record_and_session(record, session)

        for step_idx, msg in enumerate(record.messages):
            if not msg.tool_calls:
                continue
            for call in msg.tool_calls:
                for k, v in call.arguments.items():
                    if "id" not in str(k).lower():
                        continue
                    if str(v).lower() in ("unknown", "none", ""):
                        continue
                    if "dummy" in str(v).lower():
                        continue
                    if str(v) not in known_ids:
                        failures.append(
                            ValidationFailure(
                                tag="hallucinated_id",
                                description=f"Argument {k}={v} not found in session entity store.",
                                step_index=step_idx,
                            )
                        )

        return ValidationResult(is_valid=len(failures) == 0, failures=failures)
