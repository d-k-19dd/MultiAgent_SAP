"""Semantic checks: endpoint ↔ argument compatibility and intent-specific expectations."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from synthetic_tooluse.schemas.registry import EndpointDescriptor, ToolDefinition

# Intent name (lowercase) -> endpoint id must start with one of these prefixes
INTENT_ENDPOINT_PREFIXES: Dict[str, List[str]] = {
    "trip planning": ["Travel/"],
    "budgeting and finance": ["Finance/"],
    "savings and cash flow": ["Finance/"],
    "schedule and productivity": ["Productivity/"],
    "account management": ["Account/"],
    "research and information": ["Knowledge/"],
}

_HOTEL_ID_LIKE = re.compile(r"^hot_[a-z0-9]{4,}$", re.I)


def _lookup_endpoint(ep_id: str, registry: Optional[List[ToolDefinition]]) -> Optional[EndpointDescriptor]:
    if not registry:
        return None
    for t in registry:
        for e in t.endpoints:
            if e.endpoint_id == ep_id:
                return e
    return None


def audit_tool_call(
    endpoint_id: str,
    arguments: Dict[str, Any],
    intent_name: Optional[str],
    registry: Optional[List[ToolDefinition]],
) -> List[str]:
    """
    Returns human-readable violation strings (empty if OK).
    """
    violations: List[str] = []
    ep_lower = endpoint_id.lower()
    ep_def = _lookup_endpoint(endpoint_id, registry)

    allowed_param_names = {p.name for p in ep_def.input_parameters} if ep_def else set()

    if ep_def and allowed_param_names:
        for k in arguments.keys():
            if k not in allowed_param_names:
                violations.append(f"Unexpected argument '{k}' for endpoint {endpoint_id}")

    if "search_hotels" in ep_lower:
        if "hotel_id" in arguments:
            violations.append("search_hotels must not receive hotel_id; use city and dates.")
        city = arguments.get("city")
        if isinstance(city, str) and _HOTEL_ID_LIKE.match(city.strip()):
            violations.append("search_hotels 'city' must not be a hotel_id-like value.")
        for bad_key in ("hotelid", "hotel", "property_id"):
            if bad_key in {x.lower() for x in arguments.keys()}:
                violations.append(f"search_hotels should not use {bad_key} as a stand-in for city.")

    if "search_flights" in ep_lower:
        if "hotel_id" in {k.lower() for k in arguments}:
            violations.append("search_flights must not receive hotel_id.")

    intent_key = (intent_name or "").strip().lower()
    prefixes = INTENT_ENDPOINT_PREFIXES.get(intent_key)
    if prefixes and not any(endpoint_id.startswith(p) for p in prefixes):
        violations.append(
            f"Endpoint {endpoint_id} does not match expected prefixes {prefixes} for intent '{intent_name}'."
        )

    # Productivity: disallow Knowledge summarization as primary tool in scheduling flows
    if intent_key == "schedule and productivity":
        if "summarize_content" in ep_lower or "search_articles" in ep_lower:
            violations.append("Scheduling intent should use schedule/reminder/calendar tools, not article/summary APIs.")

    return violations


def summarize_order_violations(
    ordered_endpoints: List[str],
    intent_key: str,
) -> List[str]:
    """e.g. summarize_content without prior search_articles for research intent."""
    violations: List[str] = []
    if intent_key != "research and information":
        return violations
    saw_search = False
    for ep in ordered_endpoints:
        el = ep.lower()
        if "search_articles" in el:
            saw_search = True
        if "summarize_content" in el and not saw_search:
            violations.append("summarize_content ran before any search_articles in the trace.")
            break
    return violations
