"""Hard cap on tool calls per conversation."""

from __future__ import annotations

from typing import Optional

# Minimum floor per intent (actual budget is max of difficulty base and this floor, capped globally).
_INTENT_EXECUTION_FLOOR: dict[str, int] = {
    "trip planning": 6,
    "budgeting and finance": 5,
    "savings and cash flow": 5,
    "schedule and productivity": 5,
    "account management": 4,
    "research and information": 4,
}

_GLOBAL_EXEC_CAP = 8


def execution_budget_for_difficulty(difficulty_level: str) -> int:
    d = (difficulty_level or "medium").strip().lower()
    if d == "simple":
        return 2
    if d == "complex":
        return 4
    return 3


def compute_pipeline_execution_budget(
    difficulty_level: str,
    intent_name: Optional[str],
    require_multi_tool: bool,
) -> int:
    """
    Max tool executions allowed for this trace: combines difficulty, intent complexity,
    and multi-tool pacing. Capped at _GLOBAL_EXEC_CAP.
    """
    base = execution_budget_for_difficulty(difficulty_level)
    key = (intent_name or "").strip().lower()
    intent_floor = _INTENT_EXECUTION_FLOOR.get(key, base)
    n = max(base, intent_floor, 2)
    if require_multi_tool:
        n = max(n, 4)
    return min(n, _GLOBAL_EXEC_CAP)
