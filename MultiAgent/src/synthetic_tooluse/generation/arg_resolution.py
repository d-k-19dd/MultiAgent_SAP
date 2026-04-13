"""Ground tool arguments from session state, context IDs, and safe defaults."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from synthetic_tooluse.execution.state import SessionState
from synthetic_tooluse.schemas.registry import EndpointDescriptor

# Sensible defaults when no prior tool output exists (deterministic, schema-valid).
_HOTEL_ID_LIKE = re.compile(r"^hot_[a-z0-9]{4,}$", re.I)

_PARAM_DEFAULTS: Dict[str, Any] = {
    "origin_airport": "SFO",
    "destination_airport": "JFK",
    "departure_date": "2026-06-01",
    "city": "San Francisco",
    "check_in": "2026-06-02",
    "check_out": "2026-06-06",
    "guest_name": "Alex User",
    "interests": "museums,food",
    "start_date": "2026-06-02",
    "income_monthly": 8000,
    "fixed_costs_monthly": 4500,
    "currency": "USD",
    "category": "groceries",
    "amount": 120,
    "goal_amount": 5000,
    "horizon_months": 12,
    "day": "2026-06-10",
    "start_time": "09:00",
    "end_time": "10:30",
    "title": "Deep work block",
    "remind_at": "2026-06-10T08:45:00",
    "channel": "push",
    "start": "2026-06-10T09:00:00",
    "end": "2026-06-10T10:30:00",
    "user_email": "alex@example.com",
    "payment_method_token": "tok_visa_4242",
    "billing_zip": "94107",
    "query": "renewable energy policy overview",
    "max_results": 5,
    "max_words": 200,
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _value_from_context(param_name: str, ctx: Dict[str, Any]) -> Optional[Any]:
    pn = param_name.lower()
    pn_compact = _norm(param_name)
    best = None
    best_score = 0
    for k, v in ctx.items():
        kl = str(k).lower()
        kc = _norm(str(k))
        score = 0
        if pn == kl:
            score = 100
        elif pn in kl or kl in pn:
            score = 50
        elif pn_compact and (pn_compact in kc or kc in pn_compact):
            score = 40
        elif "id" in pn and "id" in kl:
            score = 25
        if score > best_score:
            best_score = score
            best = v
    return best if best_score >= 25 else None


def _latest_id_from_session(session: SessionState) -> Optional[str]:
    if not session.entity_store.id_to_type:
        return None
    # Deterministic: last inserted id
    return list(session.entity_store.id_to_type.keys())[-1]


def build_arguments_for_endpoint(
    ep: EndpointDescriptor,
    session: SessionState,
    context_state: Dict[str, Any],
) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for p in ep.input_parameters:
        name = p.name
        val = _value_from_context(name, context_state)
        if val is None:
            val = session.extracted_slots.get(name)
        if val is None and "id" in name.lower():
            val = _value_from_context(name, session.extracted_slots)  # type: ignore[arg-type]
        if val is None and p.required:
            if "id" in name.lower():
                val = _latest_id_from_session(session) or "unknown"
            else:
                val = _PARAM_DEFAULTS.get(name)
        if val is None and not p.required:
            val = _PARAM_DEFAULTS.get(name)
        if val is not None:
            args[name] = val

    el = ep.endpoint_id.lower()
    if "search_hotels" in el:
        args.pop("hotel_id", None)
        args.pop("hotelid", None)
        for k in list(args.keys()):
            if k.lower() in ("property_id", "listing_id"):
                args.pop(k, None)
        city = args.get("city")
        if isinstance(city, str) and _HOTEL_ID_LIKE.match(city.strip()):
            args["city"] = _PARAM_DEFAULTS.get("city", "San Francisco")

    return args
