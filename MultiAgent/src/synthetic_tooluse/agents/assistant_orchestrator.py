import json
from typing import List, Dict, Any, Optional

from pydantic import BaseModel

from synthetic_tooluse.schemas.graph import ChainPlan, ChainStep
from synthetic_tooluse.agents.base import BaseAgent
from synthetic_tooluse.config import USE_MOCK_LLM


class AssistantToolCall(BaseModel):
    endpoint: str
    arguments_json: str


class ToolCallResponse(BaseModel):
    clarification_question: str
    tool_calls: List[AssistantToolCall]
    final_answer: str


class AssistantOrchestrator(BaseAgent):
    """
    Assistant agent tasked with navigating the chain,
    making tool calls, or asking clarifications.
    """

    def generate_turn(
        self,
        conversation_history: List[Dict[str, Any]],
        active_plan: ChainPlan,
        current_step: Optional[ChainStep] = None,
        forced_arguments: Optional[Dict[str, Any]] = None,
        finalize: bool = False,
    ) -> ToolCallResponse:
        intent_str = (
            f"User Intent: {active_plan.intent_name}. Context: {active_plan.intent_desc}"
            if active_plan.intent_name
            else ""
        )
        template_str = (
            f"You MUST follow this workflow pattern: '{active_plan.workflow_template}'."
            if getattr(active_plan, "workflow_template", None)
            else "Use the planned endpoints in order; advance the task each turn."
        )
        step_hint = ""
        if current_step:
            step_hint = (
                f"Current step (execute now unless required slots are truly missing): "
                f"{current_step.endpoint_id}. Required slots: {current_step.required_slots}."
            )

        system_prompt = f"""
You are a helpful assistant that completes tasks using tools.
{intent_str}
{template_str}
{step_hint}
Planned endpoints (full chain): {[s.endpoint_id for s in active_plan.steps]}

RULES:
- This turn is exactly ONE plan step: emit EXACTLY ONE tool call for the current step endpoint only.
- Do NOT batch multiple future steps into this message. Do NOT call tools out of order.
- Prefer the current step endpoint when it matches the next needed action in the chain.
- Use tools that fit the intent and domain; avoid unrelated APIs.
- Do not invent IDs: copy identifiers exactly from [SYSTEM NOTIFICATION] tool outputs.
- If required parameters are missing and cannot be inferred, ask ONE concise clarification.
- If enough information exists, emit tool_calls (no final_answer yet) for this turn.
- After the last tool has run and goals are met, use final_answer grounded in tool outputs.
- After a successful search/book/plan step, advance to the next planned action or finalize; do not re-run the same segment.
"""

        if finalize:
            fin_prompt = (
                "All planned tools have run. Provide a concise final_answer grounded ONLY in "
                "tool messages and [SYSTEM NOTIFICATION]. Do not call tools."
            )
            messages = [{"role": "system", "content": fin_prompt}] + conversation_history
            if USE_MOCK_LLM:
                return ToolCallResponse(
                    clarification_question="",
                    tool_calls=[],
                    final_answer="Here is a concise summary based on the tool results above.",
                )
            return self(messages, response_format=ToolCallResponse)

        messages = [{"role": "system", "content": system_prompt}] + conversation_history

        if USE_MOCK_LLM:
            return self._mock_step_turn(active_plan, current_step, conversation_history, forced_arguments)

        result = self(messages, response_format=ToolCallResponse)
        return result

    def _mock_step_turn(
        self,
        _plan: ChainPlan,
        current_step: Optional[ChainStep],
        conversation_history: List[Dict[str, Any]],
        forced_arguments: Optional[Dict[str, Any]],
    ) -> ToolCallResponse:
        """Deterministic tool calls for offline runs and tests."""
        if current_step is None:
            return ToolCallResponse(
                clarification_question="",
                tool_calls=[],
                final_answer="",
            )

        user_turns = sum(1 for m in conversation_history if m.get("role") == "user")
        if current_step.likely_needs_clarification and user_turns < 2:
            return ToolCallResponse(
                clarification_question="Could you confirm dates or destination so I can run the tools?",
                tool_calls=[],
                final_answer="",
            )

        args = forced_arguments or {}
        return ToolCallResponse(
            clarification_question="",
            tool_calls=[
                AssistantToolCall(
                    endpoint=current_step.endpoint_id,
                    arguments_json=json.dumps(args),
                )
            ],
            final_answer="",
        )
