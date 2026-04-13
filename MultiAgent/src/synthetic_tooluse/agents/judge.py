from pydantic import ValidationError
from typing import List, Dict, Any, Optional
from synthetic_tooluse.agents.base import BaseAgent
from synthetic_tooluse.schemas.evaluation import JudgeScores, JudgeAnnotation
from synthetic_tooluse.config import USE_MOCK_LLM

_TOOL_CORRECTNESS_DEGRADE = frozenset(
    {
        "duplicate_tool_call",
        "repeated_workflow_block",
        "endpoint_argument_mismatch",
        "weak_endpoint_order",
        "task_restart_after_tools",
        "extraneous_tool_after_completion",
    }
)


class JudgeAgent(BaseAgent):
    """Scores generated conversations on multiple quality dimensions."""

    @staticmethod
    def _heuristic_annotation(tool_count: int, failure_tags: List[str]) -> JudgeAnnotation:
        base_tc = 4.0 if tool_count > 0 else 0.0
        if "irrelevant_tool_usage" in failure_tags or "domain_mismatch" in failure_tags:
            base_tc = 0.0
        if any(t in failure_tags for t in _TOOL_CORRECTNESS_DEGRADE):
            base_tc = min(base_tc, 2.5)
        return JudgeAnnotation(
            scores=JudgeScores(
                naturalness=4.0 if tool_count > 0 else 1.0,
                tool_correctness=base_tc,
                task_completion=4.0 if tool_count > 0 else 0.0,
                grounding_coherence=4.0 if tool_count > 0 else 1.0,
            ),
            failure_tags=[] if tool_count > 0 else ["zero_tools_penalty"],
            rationale="Heuristic judge (mock mode or parse fallback)",
        )
    
    def evaluate(self, conversation_history: List[Dict[str, Any]], failure_tags: Optional[List[str]] = None) -> JudgeAnnotation:
        if failure_tags is None:
            failure_tags = []
        tool_count = sum(1 for m in conversation_history if m.get("role") == "tool")

        if USE_MOCK_LLM:
            ann = self._heuristic_annotation(tool_count, failure_tags)
            if tool_count == 0:
                ann.scores.tool_correctness = 0.0
                ann.scores.task_completion = 0.0
            return ann
        
        failure_str = f"Warning: system flagged the following issues: {failure_tags}" if failure_tags else "System flagged no issues."
        
        prompt = f"""
        Evaluate this conversation on Naturalness, Tool Correctness, Task Completion, and Grounding Coherence.
        Provide scores 1.0 to 5.0 and failure tags if any score is low.
        {failure_str}
        If the tools used were strictly flagged as 'irrelevant_tool_usage' or 'domain_mismatch', the tool_correctness MUST be 1.0 or 0.0 even if you think it's technically fine! Task completion shouldn't score high if generic non-tool response handled the goal.
        Penalize tool_correctness heavily for: duplicate identical tool calls, repeated workflow segments, wrong arguments for an endpoint (e.g. hotel_id passed to search_hotels), restarting the task after tools already succeeded, or extra tool calls after a finished answer.
        """
        
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": str(conversation_history)}]
        
        try:
            res = self(messages, response_format=JudgeAnnotation)
        except ValidationError as exc:
            print(f"Judge structured output invalid: {exc}. Using heuristic fallback.")
            res = None
        except Exception as exc:
            print(f"Judge call failed: {exc}. Using heuristic fallback.")
            res = None
        
        if res is not None and isinstance(res, JudgeAnnotation):
            # Hard overrides against LLM bias
            if tool_count == 0:
                res.scores.tool_correctness = 0.0
                res.scores.task_completion = 0.0
                if "zero_tools_penalty" not in res.failure_tags:
                    res.failure_tags.append("zero_tools_penalty")
            
            if "irrelevant_tool_usage" in failure_tags or "domain_mismatch" in failure_tags:
                res.scores.tool_correctness = 0.0

            if any(t in failure_tags for t in _TOOL_CORRECTNESS_DEGRADE):
                res.scores.tool_correctness = min(res.scores.tool_correctness, 2.5)

            return res
            
        return self._heuristic_annotation(tool_count, failure_tags)
