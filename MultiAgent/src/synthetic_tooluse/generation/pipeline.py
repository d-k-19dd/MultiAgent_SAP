import ast
import json
import logging
import random
import uuid
from typing import Any, Dict, List

from synthetic_tooluse.schemas.conversation import ConversationRecord, Message, ToolCallRequest
from synthetic_tooluse.schemas.graph import ChainConstraints
from synthetic_tooluse.execution.state import SessionState
from synthetic_tooluse.execution.mock_engine import MockExecutionEngine
from synthetic_tooluse.graph.sampler import ChainSampler
from synthetic_tooluse.agents.user_simulator import UserSimulator
from synthetic_tooluse.agents.assistant_orchestrator import (
    AssistantOrchestrator,
    AssistantToolCall,
    ToolCallResponse,
)
from synthetic_tooluse.agents.judge import JudgeAgent
from synthetic_tooluse.agents.repair import RepairAgent
from synthetic_tooluse.generation.steering import SteeringManager
from synthetic_tooluse.generation.context_manager import ContextManager
from synthetic_tooluse.generation.validator import TraceValidator
from synthetic_tooluse.generation.intents import INTENT_CONFIGS
from synthetic_tooluse.generation.arg_resolution import build_arguments_for_endpoint
from synthetic_tooluse.generation.execution_dedupe import (
    may_execute_tool,
    record_tool_execution,
    stable_tool_signature,
)
from synthetic_tooluse.config import STRICT_PLAN_EXECUTION
from synthetic_tooluse.evaluation.trace_analyzer import analyze_record_quality

logger = logging.getLogger(__name__)


class GenerationPipeline:
    def __init__(self, registry, graph, steering_enabled: bool = True):
        self.registry = registry
        self.engine = MockExecutionEngine([ep for t in registry for ep in t.endpoints])
        self.sampler = ChainSampler(graph, registry)

        self.user_sim = UserSimulator()
        self.assistant = AssistantOrchestrator()
        self.judge = JudgeAgent()
        self.repair = RepairAgent()
        self.validator = TraceValidator()

        self.steering = SteeringManager(enabled=steering_enabled)

    def _registry_supports_strong_multi(self) -> bool:
        tool_ids = {t.tool_id for t in self.registry}
        n_eps = sum(len(t.endpoints) for t in self.registry)
        return len(tool_ids) >= 2 and n_eps >= 3

    def run_generation(self, count: int, constraints: ChainConstraints, max_retries: int = 1) -> List[ConversationRecord]:
        results: List[ConversationRecord] = []
        dataset_multi_tool_count = 0

        inner_retries = max(3, max_retries)

        for i in range(count):
            ratio = dataset_multi_tool_count / max(1, i)
            logger.info("Generating sample %d/%d (multi-tool ratio so far=%.3f)", i + 1, count, ratio)
            print(f"Generating conversation {i+1}/{count}... (Current Multi-Tool Ratio: {ratio:.2f})")

            if ratio < 0.60 and self._registry_supports_strong_multi():
                constraints.require_multi_tool = True
            else:
                constraints.require_multi_tool = False

            for _retry in range(inner_retries):
                intent = random.choice(INTENT_CONFIGS)
                constraints.intent_name = intent.name
                constraints.intent_desc = intent.description
                constraints.positive_keywords = list(intent.positive_keywords)
                constraints.negative_keywords = list(intent.negative_keywords)
                constraints.required_domains = list(intent.primary_domains)
                constraints.workflow_template = random.choice(intent.workflow_templates) if intent.workflow_templates else None

                plan = self.sampler.sample(constraints)
                planned_eps = [s.endpoint_id for s in plan.steps]
                logger.info(
                    "sample debug: intent=%r domains=%r planned_endpoints=%s template=%r",
                    intent.name,
                    intent.primary_domains,
                    planned_eps,
                    constraints.workflow_template,
                )

                session = SessionState()
                context = ContextManager()
                history: List[Dict[str, Any]] = []
                real_endpoint_map: Dict[str, str] = {}

                user_msg = self.user_sim.generate_initial_request(plan)
                history.append({"role": "user", "content": user_msg})

                tools_used = set()
                endpoints_used: List[str] = []
                execution_counts: Dict[str, int] = {}
                duplicate_steps_skipped = 0

                if STRICT_PLAN_EXECUTION:
                    for step_index, step in enumerate(plan.steps):
                        ep_def = self.engine.endpoints.get(step.endpoint_id)
                        if not ep_def:
                            logger.error("Missing endpoint in engine: %s", step.endpoint_id)
                            continue
                        forced_args = build_arguments_for_endpoint(ep_def, session, context.state)
                        sig = stable_tool_signature(step.endpoint_id, forced_args)
                        ok, reason = may_execute_tool(sig, bool(step.retryable), execution_counts)
                        if not ok:
                            duplicate_steps_skipped += 1
                            logger.info(
                                "Skipping duplicate execution (%s): %s",
                                reason,
                                step.endpoint_id,
                            )
                            continue
                        call_id = f"call_{uuid.uuid4().hex[:8]}"
                        args_str = json.dumps(forced_args)
                        clean_name = step.endpoint_id.replace("/", "_").replace(".", "_")[:64]
                        real_endpoint_map[call_id] = step.endpoint_id
                        history.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {"name": clean_name, "arguments": args_str},
                                    }
                                ],
                            }
                        )
                        endpoints_used.append(step.endpoint_id)
                        parts = step.endpoint_id.split("/")
                        tools_used.add("/".join(parts[:-1]) if len(parts) > 1 else "unk")
                        out = self.engine.execute(step.endpoint_id, forced_args, session)
                        record_tool_execution(sig, execution_counts)
                        context.extract_from_output(out)
                        session.update_slots(dict(context.state))
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": clean_name,
                                "content": str(out),
                            }
                        )
                        logger.debug(
                            "strict chain: step %d/%d executed %s",
                            step_index + 1,
                            len(plan.steps),
                            step.endpoint_id,
                        )
                else:
                    for step in plan.steps:
                        context_str = context.formulate_context_prompt()
                        ast_in = history + [{"role": "system", "content": context_str}]

                        ep_def = self.engine.endpoints.get(step.endpoint_id)
                        forced_args = (
                            build_arguments_for_endpoint(ep_def, session, context.state) if ep_def else {}
                        )

                        resp = self.assistant.generate_turn(
                            ast_in,
                            plan,
                            current_step=step,
                            forced_arguments=forced_args,
                        )

                        clarification_turns = 0
                        while resp.clarification_question and clarification_turns < 2:
                            history.append({"role": "assistant", "content": resp.clarification_question})
                            user_reply = self.user_sim.generate_reply(history, plan)
                            history.append({"role": "user", "content": user_reply})
                            ast_in = history + [{"role": "system", "content": context_str}]
                            resp = self.assistant.generate_turn(
                                ast_in,
                                plan,
                                current_step=step,
                                forced_arguments=forced_args,
                            )
                            clarification_turns += 1

                        if resp.tool_calls and len(resp.tool_calls) > 1:
                            logger.warning(
                                "LLM emitted %d tool calls for one plan step; enforcing single call for %s",
                                len(resp.tool_calls),
                                step.endpoint_id,
                            )
                            resp = ToolCallResponse(
                                clarification_question="",
                                tool_calls=[
                                    AssistantToolCall(
                                        endpoint=step.endpoint_id,
                                        arguments_json=json.dumps(forced_args),
                                    )
                                ],
                                final_answer="",
                            )

                        if resp.clarification_question or not resp.tool_calls:
                            resp = ToolCallResponse(
                                clarification_question="",
                                tool_calls=[
                                    AssistantToolCall(
                                        endpoint=step.endpoint_id,
                                        arguments_json=json.dumps(forced_args),
                                    )
                                ],
                                final_answer="",
                            )

                        if resp.tool_calls:
                            parsed_tc_map: List[Dict[str, Any]] = []

                            for req_obj in resp.tool_calls:
                                call_id = f"call_{uuid.uuid4().hex[:8]}"
                                endpoint_val = getattr(req_obj, "endpoint", "") or step.endpoint_id
                                args_str = getattr(req_obj, "arguments_json", "{}") or "{}"
                                try:
                                    args = json.loads(args_str)
                                except json.JSONDecodeError:
                                    try:
                                        args = ast.literal_eval(args_str)
                                        if not isinstance(args, dict):
                                            args = {}
                                    except Exception:
                                        args = {}
                                if endpoint_val != step.endpoint_id:
                                    logger.warning(
                                        "LLM chose %s but plan requires %s; forcing planned endpoint",
                                        endpoint_val,
                                        step.endpoint_id,
                                    )
                                    endpoint_val = step.endpoint_id
                                    args = forced_args
                                args_str = json.dumps(args)

                                clean_name = endpoint_val.replace("/", "_").replace(".", "_")[:64]
                                parsed_tc_map.append(
                                    {
                                        "endpoint": endpoint_val,
                                        "arguments": args,
                                        "call_id": call_id,
                                        "clean_name": clean_name,
                                        "args_str": args_str,
                                    }
                                )
                                real_endpoint_map[call_id] = endpoint_val

                            to_run: List[Dict[str, Any]] = []
                            for tc_dict in parsed_tc_map:
                                sig = stable_tool_signature(tc_dict["endpoint"], tc_dict["arguments"])
                                ok, reason = may_execute_tool(sig, bool(step.retryable), execution_counts)
                                if not ok:
                                    duplicate_steps_skipped += 1
                                    logger.info(
                                        "Skipping duplicate execution (%s): %s",
                                        reason,
                                        tc_dict["endpoint"],
                                    )
                                    continue
                                to_run.append(tc_dict)

                            if not to_run:
                                logger.info(
                                    "Plan step %s had no non-duplicate tool calls; skipping turn.",
                                    step.endpoint_id,
                                )
                                continue

                            openai_tool_calls = []
                            for tc_dict in to_run:
                                openai_tool_calls.append(
                                    {
                                        "id": tc_dict["call_id"],
                                        "type": "function",
                                        "function": {
                                            "name": tc_dict["clean_name"],
                                            "arguments": tc_dict["args_str"],
                                        },
                                    }
                                )

                            history.append({"role": "assistant", "content": None, "tool_calls": openai_tool_calls})

                            for tc_dict in to_run:
                                endpoint_id = tc_dict["endpoint"]
                                args = tc_dict["arguments"]
                                call_id = tc_dict["call_id"]
                                sig = stable_tool_signature(endpoint_id, args)

                                endpoints_used.append(endpoint_id)
                                parts = endpoint_id.split("/")
                                tools_used.add("/".join(parts[:-1]) if len(parts) > 1 else "unk")

                                out = self.engine.execute(endpoint_id, args, session)
                                record_tool_execution(sig, execution_counts)
                                context.extract_from_output(out)
                                session.update_slots(dict(context.state))

                                history.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call_id,
                                        "name": endpoint_id.replace("/", "_").replace(".", "_")[:64],
                                        "content": str(out),
                                    }
                                )

                fin_ctx = context.formulate_context_prompt()
                fin_in = history + [{"role": "system", "content": fin_ctx}]
                final_resp = self.assistant.generate_turn(fin_in, plan, finalize=True)
                if final_resp.final_answer:
                    history.append({"role": "assistant", "content": final_resp.final_answer})

                messages_parsed: List[Message] = []
                for h in history:
                    parsed_tcs = None
                    if h["role"] == "assistant" and h.get("tool_calls"):
                        parsed_tcs = []
                        for tc in h.get("tool_calls", []):
                            if isinstance(tc, dict) and "function" in tc:
                                try:
                                    arg_dict = json.loads(tc["function"]["arguments"])
                                except Exception:
                                    arg_dict = {}
                                tc_id = tc.get("id")
                                unscrubbed = real_endpoint_map.get(tc_id, tc["function"]["name"])
                                parsed_tcs.append(ToolCallRequest(endpoint=unscrubbed, arguments=arg_dict))
                    messages_parsed.append(
                        Message(
                            role=h["role"],
                            content=str(h["content"]) if h.get("content") is not None else None,
                            tool_calls=parsed_tcs,
                        )
                    )

                record = ConversationRecord(
                    conversation_id=f"conv_{uuid.uuid4().hex[:8]}",
                    messages=messages_parsed,
                    metadata={
                        "endpoints_used": endpoints_used,
                        "tools_used": list(tools_used),
                        "num_turns": len(history),
                        "num_tool_calls": len(endpoints_used),
                        "num_distinct_tools": len(tools_used),
                        "intended_multi_tool": getattr(constraints, "require_multi_tool", False),
                        "actual_num_calls": len(endpoints_used),
                        "actual_num_distinct": len(tools_used),
                        "workflow_template": getattr(plan, "workflow_template", None),
                        "steering_enabled": self.steering.enabled,
                        "model": self.assistant.model,
                        "repair_attempts": 0,
                        "failure_tags": [],
                        "user_intent": intent.name,
                        "inferred_domains": list(intent.primary_domains),
                        "planned_endpoints": planned_eps,
                        "filtered_tool_count": len(planned_eps),
                        "strict_plan_execution": STRICT_PLAN_EXECUTION,
                        "planned_num_steps": len(plan.steps),
                        "executed_num_steps": len(endpoints_used),
                        "duplicate_steps_skipped": duplicate_steps_skipped,
                    },
                )
                record.metadata.update(analyze_record_quality(record))

                validation_res = self.validator.validate(record, session, plan, registry=self.registry)
                if not validation_res.is_valid:
                    tags = [f.tag for f in validation_res.failures]
                    record.metadata["failure_tags"].extend(tags)
                    record.metadata["rejection_reason"] = "validation_failed"
                    logger.warning("validation failed: %s", tags)
                    record = self.repair.attempt_repair(
                        record,
                        f"Validation Failures: {tags}",
                        plan,
                        engine=self.engine,
                    )

                judge_hist = [m.model_dump(exclude_none=True) for m in record.messages]
                judge_res = self.judge.evaluate(judge_hist, record.metadata.get("failure_tags", []))
                record.judge_scores = judge_res.scores.model_dump()

                mean_score = sum(record.judge_scores.values()) / max(1, len(record.judge_scores))
                if mean_score < 4.0:
                    record.metadata["failure_tags"].extend(judge_res.failure_tags)
                    record.metadata["rejection_reason"] = "low_judge_score"
                    logger.info("low judge score (mean=%.2f): %s", mean_score, judge_res.failure_tags)
                    record = self.repair.attempt_repair(
                        record,
                        f"Low judge score. Info: {judge_res.failure_tags}",
                        plan,
                        engine=self.engine,
                    )

                self.steering.update_stats(plan, len(history))

                if len(tools_used) == 0:
                    record.metadata["failure_tags"].append("zero_tool_calls")
                    record.metadata["rejection_reason"] = "zero_tool_calls"
                    logger.warning("regenerating: zero tool calls")
                    continue

                if "low_diversity" in record.metadata.get("failure_tags", []):
                    record.metadata["rejection_reason"] = "low_diversity"
                    logger.warning("regenerating: low diversity")
                    continue

                if record.metadata.get("actual_num_calls", 0) >= 3 and record.metadata.get("actual_num_distinct", 0) >= 2:
                    dataset_multi_tool_count += 1

                record.metadata.pop("rejection_reason", None)
                results.append(record)
                break
            else:
                logger.error(
                    "Exhausted %d retries for sample %d without an accepted record",
                    inner_retries,
                    i + 1,
                )

        return results
