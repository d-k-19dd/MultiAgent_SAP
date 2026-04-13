import json
import uuid
from typing import Any, Dict, List, Optional

from synthetic_tooluse.schemas.conversation import ConversationRecord, Message, ToolCallRequest
from synthetic_tooluse.agents.base import BaseAgent
from synthetic_tooluse.agents.assistant_orchestrator import AssistantOrchestrator
from synthetic_tooluse.schemas.graph import ChainPlan
from synthetic_tooluse.execution.mock_engine import MockExecutionEngine
from synthetic_tooluse.execution.state import SessionState
from synthetic_tooluse.generation.context_manager import ContextManager
from synthetic_tooluse.generation.arg_resolution import build_arguments_for_endpoint
from synthetic_tooluse.generation.execution_dedupe import (
    may_execute_tool,
    record_tool_execution,
    stable_tool_signature,
)
from synthetic_tooluse.evaluation.trace_analyzer import analyze_record_quality


class RepairAgent(BaseAgent):
    """Targeted repair: optional full trace rebuild from plan; otherwise LLM-assisted text fix."""

    @staticmethod
    def _compress_duplicate_blocks(record: ConversationRecord) -> ConversationRecord:
        """Remove repeated assistant+tool pairs with identical (endpoint, args)."""
        msgs = list(record.messages)
        new_msgs: List[Message] = []
        seen_blocks: set[str] = set()
        i = 0
        while i < len(msgs):
            m = msgs[i]
            if (
                m.role == "assistant"
                and m.tool_calls
                and len(m.tool_calls) == 1
                and i + 1 < len(msgs)
                and msgs[i + 1].role == "tool"
            ):
                tc = m.tool_calls[0]
                sig = stable_tool_signature(tc.endpoint, tc.arguments)
                if sig in seen_blocks:
                    i += 2
                    continue
                seen_blocks.add(sig)
                new_msgs.append(m)
                new_msgs.append(msgs[i + 1])
                i += 2
                continue
            new_msgs.append(m)
            i += 1

        endpoints_used: List[str] = []
        tools_used: set[str] = set()
        for m in new_msgs:
            if m.role != "assistant" or not m.tool_calls:
                continue
            for tc in m.tool_calls:
                endpoints_used.append(tc.endpoint)
                parts = tc.endpoint.split("/")
                tools_used.add("/".join(parts[:-1]) if len(parts) > 1 else "unk")

        record.messages = new_msgs
        meta = dict(record.metadata)
        meta["endpoints_used"] = endpoints_used
        meta["tools_used"] = list(tools_used)
        meta["num_tool_calls"] = len(endpoints_used)
        meta["actual_num_calls"] = len(endpoints_used)
        meta["num_distinct_tools"] = len(tools_used)
        meta["actual_num_distinct"] = len(tools_used)
        meta["num_turns"] = len(new_msgs)
        meta.setdefault("repair_actions", [])
        meta["repair_actions"] = list(meta["repair_actions"]) + ["compressed_duplicate_blocks"]
        record.metadata = meta
        return record

    def attempt_repair(
        self,
        record: ConversationRecord,
        failure_context: str,
        plan: Optional[ChainPlan] = None,
        engine: Optional[MockExecutionEngine] = None,
    ) -> ConversationRecord:
        record.metadata["repair_attempts"] = record.metadata.get("repair_attempts", 0) + 1
        record.metadata.setdefault("failure_tags", [])
        record.metadata["failure_tags"].append("repaired")
        record.metadata.setdefault("repair_actions", [])
        tags = list(record.metadata.get("failure_tags", []))

        compress_tags = {
            "duplicate_tool_call",
            "repeated_workflow_block",
            "extraneous_tool_after_completion",
        }
        if any(t in tags for t in compress_tags):
            record = self._compress_duplicate_blocks(record)
            record.metadata.update(analyze_record_quality(record))

        # Structural rebuild only for grounding/absence issues — not for weak multi-tool chains
        # (those should be fixed by planner/execution, not hidden by replay).
        structural_tags = {
            "zero_tool_calls",
            "hallucinated_id",
            "no_task_completion",
        }
        if plan and engine and any(t in structural_tags for t in tags):
            rebuilt = self._rebuild_trace_from_plan(record, plan, engine)
            record.metadata["repair_actions"].append("structural_rebuild_from_plan")
            return rebuilt

        intent_info = f"Intent: {plan.intent_name}. Context: {plan.intent_desc}" if plan else "Unknown"

        prompt = f"""
The following trace failed validation or judging: {failure_context}.
User True Context: {intent_info}

Perform a minimal repair:
- Replace wrong tools with ones aligned to the intent.
- Insert missing tool calls instead of restarting the whole dialogue.
- Fix IDs using values that appear verbatim in prior tool outputs.

Return only the repaired final assistant natural-language message if the issue is phrasing;
do not output JSON.
"""
        messages = [{"role": "system", "content": prompt}]
        res = self(messages)

        if record.messages and record.messages[-1].role == "assistant":
            record.messages[-1].content = res if isinstance(res, str) else "Repaired successfully."

        record.metadata["repair_actions"].append("llm_last_turn_patch")
        record.metadata["status"] = "repaired"
        return record

    def _rebuild_trace_from_plan(
        self,
        record: ConversationRecord,
        plan: ChainPlan,
        engine: MockExecutionEngine,
    ) -> ConversationRecord:
        """Deterministically replay the planned chain with grounded arguments (offline-safe)."""
        session = SessionState()
        context = ContextManager()
        messages: List[Message] = []
        endpoints_used: List[str] = []
        tools_used = set()
        real_map: Dict[str, str] = {}

        # Preserve initial user turn when present
        if record.messages and record.messages[0].role == "user":
            messages.append(record.messages[0])
        else:
            messages.append(
                Message(
                    role="user",
                    content=f"I need help with: {plan.intent_name or 'my request'}.",
                )
            )

        execution_counts: Dict[str, int] = {}
        for step in plan.steps:
            ep = step.endpoint_id
            ep_def = engine.endpoints.get(ep)
            if not ep_def:
                continue

            args = build_arguments_for_endpoint(ep_def, session, context.state)
            session.update_slots(dict(context.state))

            sig = stable_tool_signature(ep, args)
            ok, _reason = may_execute_tool(sig, bool(step.retryable), execution_counts)
            if not ok:
                continue

            call_id = f"call_{uuid.uuid4().hex[:8]}"
            real_map[call_id] = ep
            clean_name = ep.replace("/", "_").replace(".", "_")[:64]
            openai_tcs = [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": clean_name, "arguments": json.dumps(args)},
                }
            ]

            # We only store parsed messages on the record; openai_tcs kept for debugging in metadata
            messages.append(
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCallRequest(endpoint=ep, arguments=args)],
                )
            )

            out = engine.execute(ep, args, session)
            record_tool_execution(sig, execution_counts)
            context.extract_from_output(out)
            session.update_slots(dict(context.state))

            endpoints_used.append(ep)
            parts = ep.split("/")
            tools_used.add("/".join(parts[:-1]) if len(parts) > 1 else "unk")

            messages.append(
                Message(
                    role="tool",
                    content=str(out),
                )
            )

        orch = AssistantOrchestrator()
        hist: List[Dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                hist.append({"role": "user", "content": m.content or ""})
            elif m.role == "tool":
                hist.append({"role": "tool", "content": m.content or ""})
        context_str = context.formulate_context_prompt()
        final_resp = orch.generate_turn(
            hist + [{"role": "system", "content": context_str}],
            plan,
            current_step=None,
            finalize=True,
        )
        if final_resp.final_answer:
            messages.append(Message(role="assistant", content=final_resp.final_answer))

        new_meta = dict(record.metadata)
        new_meta.update(
            {
                "endpoints_used": endpoints_used,
                "tools_used": list(tools_used),
                "num_turns": len(messages),
                "num_tool_calls": len(endpoints_used),
                "num_distinct_tools": len(tools_used),
                "actual_num_calls": len(endpoints_used),
                "actual_num_distinct": len(tools_used),
                "failure_tags": [t for t in new_meta.get("failure_tags", []) if t != "repaired"] + ["repaired"],
                "status": "repaired_structural",
                "real_endpoint_map": real_map,
            }
        )

        rebuilt = ConversationRecord(
            conversation_id=f"conv_{uuid.uuid4().hex[:8]}",
            messages=messages,
            metadata=new_meta,
            judge_scores=dict(record.judge_scores),
        )
        rebuilt.metadata.update(analyze_record_quality(rebuilt))
        return rebuilt
