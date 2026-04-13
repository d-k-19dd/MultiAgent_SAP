# Walkthrough: what lives where

A relaxed tour of the repo—read this when you open the codebase for the first time or come back after a break.

---

## Start here

- **`README.md`** — install, build, generate Run A / Run B, evaluate.
- **`DESIGN.md`** — why planner, mock engine, and agents are separate.
- **`data/raw_tools.json`** — your source tool definitions (edit this, then rebuild).
- **`artifacts/`** — generated `registry.json` after `build` (safe to delete and rebuild).

---

## The three CLI commands

All of them live in `src/synthetic_tooluse/cli.py`:

1. **`build`** — reads JSON tools, normalizes, writes `registry.json`, builds and prints graph stats.
2. **`generate`** — loads registry, rebuilds graph, runs `GenerationPipeline`, writes one JSON object per line (JSONL).
3. **`evaluate`** — reads that JSONL, aggregates metadata + judge scores into a JSON report.

If you are debugging, you can run the same module with `PYTHONPATH=src python -m synthetic_tooluse.cli …`.

---

## Generation: follow the data

Rough call order:

1. **`generation/intents.py`** — picks a `ScenarioIntent` (name, description, domains, keywords, workflow templates).
2. **`graph/sampler.py`** — thin wrapper around **`generation/chain_planner.py`**, which either uses **template chains** for the intent or a **graph random walk**.
3. **`generation/pipeline.py`** — the main loop: user message → tool calls (strict or orchestrated) → mock execution → context updates → final assistant message → validate → judge → maybe repair.
4. **`execution/mock_engine.py`** — runs the tool call and returns a string (often dict-like) result.
5. **`generation/context_manager.py`** + **`execution/state.py`** — extract IDs/slots from outputs so the next call’s arguments are grounded.

Supporting pieces you might touch:

- **`generation/arg_resolution.py`** — fills arguments from context/session/defaults.
- **`generation/execution_dedupe.py`** — avoids repeating identical `(endpoint, args)` unless a step is marked retryable.
- **`generation/validator.py`** — flags duplicates, domain mismatches, weak chains, etc.
- **`agents/repair.py`** — tries to fix a failed trace when validation or judge scores are poor.
- **`agents/judge.py`** — scores the finished dialogue on a few rubric dimensions.

---

## Agents folder

| File | Role |
|------|------|
| `user_simulator.py` | Opens the conversation and can answer clarifications. |
| `assistant_orchestrator.py` | Produces tool calls or final answers from history + plan (when not in strict executor-only path). |
| `judge.py` | Offline quality scores on the transcript. |
| `repair.py` | Second pass to patch obvious issues. |
| `base.py` | Shared LLM / mock wiring. |

---

## Schemas

Under `src/synthetic_tooluse/schemas/`:

- **`registry.py`** — tools, endpoints, parameters.
- **`graph.py`** — `ChainPlan`, `ChainStep`, `ChainConstraints`.
- **`conversation.py`** — messages, tool calls, `ConversationRecord`.
- **`evaluation.py`** — validation result types.

These are the contracts between normalize → plan → generate → evaluate.

---

## Config and behavior toggles

- **`src/synthetic_tooluse/config.py`** — reads `.env`, sets mock vs real LLM, **strict plan execution**, default model names.
- **Strict execution** — when on (default), the pipeline walks the plan’s endpoints in order with resolved arguments; good for clean traces and tests.

---

## Tests

- **`tests/e2e/`** — builds from fixture data and runs a short generate path.
- **`tests/unit/`** — smaller pieces (e.g. registry).

Run `pytest` from the repo root; `pyproject.toml` points pytest at `tests` and adds `src` to the path.

---

## Suggested workflow for you

1. Edit **`data/raw_tools.json`** if you change tools.
2. **`synthetic-tooluse build …`**
3. **`synthetic-tooluse generate …`** twice (Run A / Run B) if you want to compare steering.
4. **`synthetic-tooluse evaluate …`** on each JSONL.
5. Open the report JSON and your JSONL in a viewer; use `metadata` on each record (endpoints used, failure tags, judge scores) to see what failed and why.

That’s the whole loop—everything else is detail you can discover file by file using this map.
