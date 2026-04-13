"""Counters for a single generation run (parse retries, fallbacks, tool-name fixes)."""
from __future__ import annotations

from typing import Any, Dict


class GenerationTelemetry:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.parse_retries: int = 0
        self.parse_failures: int = 0
        self.mock_llm_fallbacks: int = 0
        self.invalid_function_name_fixes: int = 0
        self.zero_tool_failures: int = 0
        self.zero_tool_by_reason: Dict[str, int] = {}

    def record_parse_retry(self) -> None:
        self.parse_retries += 1

    def record_parse_failure(self) -> None:
        self.parse_failures += 1

    def record_mock_fallback(self) -> None:
        self.mock_llm_fallbacks += 1

    def record_invalid_function_name_fix(self) -> None:
        self.invalid_function_name_fixes += 1

    def record_zero_tool(self, reason: str) -> None:
        self.zero_tool_failures += 1
        self.zero_tool_by_reason[reason] = self.zero_tool_by_reason.get(reason, 0) + 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "parse_failures": self.parse_failures,
            "parse_retries": self.parse_retries,
            "mock_llm_fallbacks": self.mock_llm_fallbacks,
            "invalid_function_name_fixes": self.invalid_function_name_fixes,
            "zero_tool_failures": self.zero_tool_failures,
            "zero_tool_by_reason": dict(self.zero_tool_by_reason),
        }


# Process-wide singleton for BaseAgent + pipeline (one run at a time per CLI invocation)
telemetry = GenerationTelemetry()
