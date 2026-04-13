# Design notes

This document explains **why the system is shaped the way it is**, in plain language. It matches the current code under `src/synthetic_tooluse/`.

---

## The problem we’re solving

Multi-step tool use is easy to get wrong: models invent IDs, skip steps, or call tools that do not fit the user’s goal. This pipeline **separates structure from chit-chat**:

- **Structure** (which endpoints, in what order, with what slots) comes from typed data and graph logic as much as possible.
- **Language** (user asks, assistant explains, judge scores) sits in a thin agent layer that still respects the plan when strict mode is on.

---

## End-to-end flow

1. **Normalize** messy tool JSON into strict **Pydantic** models (`registry/normalizer.py`). That gives you consistent parameters and response hints.
2. **Build a directed graph** (`graph/builder.py`): endpoints are nodes; edges encode plausible hand-offs (e.g. output IDs feeding later inputs).
3. **Pick an intent** per sample (`generation/intents.py`): domains, positive/negative keywords, and workflow templates that downstream prompts can reuse.
4. **Plan a chain** (`generation/chain_planner.py`):
   - For known intents, prefer **curated template paths** (`PREDEFINED_CHAINS`).
   - Otherwise fall back to a **keyword-aware random walk** on the graph under `ChainConstraints`.
5. **Run the conversation** (`generation/pipeline.py`):
   - User simulator opens; assistant (and/or strict executor) issues tool calls; **mock engine** returns deterministic, schema-flavored payloads.
   - **Context manager** and **session state** carry forward IDs and slots so later arguments are not pure fiction.
6. **Validate, judge, optionally repair** (`generation/validator.py`, `agents/judge.py`, `agents/repair.py`) so bad traces get tagged or patched instead of silently shipping.

---

## Why split “planner” and “assistant”?

If one model both improvises dialogue **and** decides the full tool path, it often drops constraints mid-trace. The **chain planner** commits to an ordered list of endpoints first; in **strict plan execution** (`config.STRICT_PLAN_EXECUTION`, on by default), the pipeline executes that plan with grounded arguments. That keeps traces **reproducible** and easier to validate.

When strict mode is off, the orchestrator still gets nudged by the plan, but you accept more divergence—useful for stress-testing prompts.

---

## Mock execution instead of “the model imagines JSON”

The **mock engine** (`execution/mock_engine.py`) owns fake responses. That avoids the assistant “writing” its own tool output and accidentally papering over missing fields or invalid IDs. Grounding comes from **argument resolution** (`generation/arg_resolution.py`) plus whatever the engine puts in **session / entity store** (`execution/state.py`).

---

## Intents and the graph

Intents are not just labels. They supply **domains** and **keywords** so the planner’s graph walk does not wander into obviously wrong neighborhoods (e.g. lyrics APIs on a trip-planning scenario). The validator also checks endpoints against intent **negative keywords** when something slips through.

---

## Steering (Run A vs Run B)

The CLI flag `--cross-conversation-steering` toggles whether `SteeringManager` is **enabled** in `GenerationPipeline`. Today it **records** domain, endpoint, and chain usage after each accepted trace. The hook `get_sampler_weights()` is a placeholder that returns an empty dict—so flipping steering mostly affects **future wiring**, not heavy reweighting in the sampler yet. Run A / Run B are still useful as a **consistent experiment switch** as that logic grows.

---

## Quality and metrics

- **Corpus metrics** (`evaluation/metrics.py`): endpoint entropy, unique chain ratio from `endpoints_used` in metadata.
- **`evaluate` command** (`cli.py`): merges those with mean judge dimensions (naturalness, tool correctness, task completion, grounding) and **multi_tool_ratio** (share of traces with ≥3 calls and ≥2 distinct tools).

Expect a tension: pushing diversity can surface weaker or rarer tools if descriptions are thin—worth watching `tool_correctness` alongside entropy.

---

## Configuration highlights

| Concern | Where |
|--------|--------|
| API keys vs mock LLM | `config.py` (`USE_MOCK_LLM`) |
| Strict step-by-step execution | `SYNTH_STRICT_PLAN_EXECUTION` env → `STRICT_PLAN_EXECUTION` |
| Default models | `DEFAULT_GENERATION_MODEL`, `DEFAULT_JUDGE_MODEL` |

---

## Limitations (honest)

- Graph edges depend on **heuristic** alignment between outputs and expected inputs (often ID-shaped fields). Real APIs with opaque or nested names would need richer mapping.
- **Steering** is lightweight today; treat frequency stats as telemetry unless you extend the sampler to consume weights.
- **Judge / repair** quality depends on model or mock behavior; mock mode is for structure, not production subjective quality.

---

## Determinism

`generate` seeds Python’s `random` module from `--seed`. Mock mode and fixed plans make runs **repeatable** for debugging; real LLM calls add natural variance even with the same seed.
