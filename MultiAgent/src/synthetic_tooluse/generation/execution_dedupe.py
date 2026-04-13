"""Deduplicate tool executions: same endpoint + identical arguments run at most once unless step.retryable."""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def stable_tool_signature(endpoint_id: str, arguments: Dict[str, Any]) -> str:
    """Stable key for (endpoint, args) equality."""
    payload = json.dumps(arguments or {}, sort_keys=True, default=str)
    return f"{endpoint_id}::{payload}"


def may_execute_tool(
    signature: str,
    retryable: bool,
    execution_counts: Dict[str, int],
) -> Tuple[bool, str]:
    """
    Returns (allowed, reason).
    - First occurrence: allowed.
    - Second occurrence: allowed only if this step is retryable (one replay).
    - Further repeats: blocked.
    """
    n = execution_counts.get(signature, 0)
    if n == 0:
        return True, "first"
    if n >= 2:
        return False, "max_replays"
    if n == 1 and retryable:
        return True, "retry"
    return False, "duplicate_blocked"


def record_tool_execution(signature: str, execution_counts: Dict[str, int]) -> None:
    execution_counts[signature] = execution_counts.get(signature, 0) + 1
