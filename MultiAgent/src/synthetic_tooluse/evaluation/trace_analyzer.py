"""Corpus-level trace quality signals (duplicates, repeated segments, post-final tools)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from synthetic_tooluse.schemas.conversation import ConversationRecord, ToolCallRequest
from synthetic_tooluse.generation.execution_dedupe import stable_tool_signature


def iter_tool_calls_in_order(record: ConversationRecord) -> List[Tuple[int, ToolCallRequest]]:
    out: List[Tuple[int, ToolCallRequest]] = []
    for idx, msg in enumerate(record.messages):
        if msg.role != "assistant" or not msg.tool_calls:
            continue
        for tc in msg.tool_calls:
            out.append((idx, tc))
    return out


def count_duplicate_signatures(record: ConversationRecord) -> int:
    """Number of tool calls whose (endpoint, args) signature was already seen earlier in the trace."""
    seen: set[str] = set()
    dup = 0
    for _idx, tc in iter_tool_calls_in_order(record):
        sig = stable_tool_signature(tc.endpoint, tc.arguments)
        if sig in seen:
            dup += 1
        else:
            seen.add(sig)
    return dup


def has_repeated_workflow_segment(endpoints_used: List[str], min_segment: int = 2) -> bool:
    """True if the tail of the endpoint sequence repeats an immediately preceding block (e.g. A,B,A,B)."""
    eps = list(endpoints_used)
    n = len(eps)
    if n < min_segment * 2:
        return False
    for length in range(min_segment, n // 2 + 1):
        if eps[-length:] == eps[-2 * length : -length]:
            return True
    return False


def extraneous_tools_after_final_answer(record: ConversationRecord) -> bool:
    """
    True if a substantial assistant-only message appears, then later another assistant issues tool calls.
    """
    msgs = record.messages
    last_substantial_final_idx: int | None = None
    for i, m in enumerate(msgs):
        if m.role != "assistant":
            continue
        if m.tool_calls:
            continue
        text = (m.content or "").strip()
        if len(text) >= 40:
            last_substantial_final_idx = i
    if last_substantial_final_idx is None:
        return False
    for j in range(last_substantial_final_idx + 1, len(msgs)):
        m = msgs[j]
        if m.role == "assistant" and m.tool_calls:
            return True
    return False


def analyze_record_quality(record: ConversationRecord) -> Dict[str, Any]:
    """Attachable metadata / report fields for one conversation."""
    eps = list(record.metadata.get("endpoints_used", []))
    dups = count_duplicate_signatures(record)
    return {
        "duplicate_tool_calls_in_trace": dups,
        "has_repeated_workflow_block": has_repeated_workflow_segment(eps),
        "extraneous_tools_after_final_answer": extraneous_tools_after_final_answer(record),
    }


def aggregate_corpus_signals(records: List[ConversationRecord]) -> Dict[str, Any]:
    total_dup = 0
    rep_wf = 0
    ext_final = 0
    for r in records:
        m = r.metadata
        d = m.get("duplicate_tool_calls_in_trace")
        if d is None:
            d = count_duplicate_signatures(r)
        total_dup += int(d)
        wf = m.get("has_repeated_workflow_block")
        if wf is None:
            wf = has_repeated_workflow_segment(list(m.get("endpoints_used", [])))
        if wf:
            rep_wf += 1
        ex = m.get("extraneous_tools_after_final_answer")
        if ex is None:
            ex = extraneous_tools_after_final_answer(r)
        if ex:
            ext_final += 1
    n = max(1, len(records))
    return {
        "total_duplicate_tool_calls": total_dup,
        "conversations_with_repeated_workflow_block": rep_wf,
        "conversations_with_extraneous_tools_after_final": ext_final,
        "repeated_workflow_block_ratio": rep_wf / n,
        "extraneous_tools_after_final_ratio": ext_final / n,
        "mean_duplicate_tool_calls_per_conversation": total_dup / n,
    }
