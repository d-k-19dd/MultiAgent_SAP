# Synthetic tool-use conversations

This project helps you **generate synthetic multi-turn chats** where an assistant calls tools in a believable order, with arguments grounded in mock API responses. Think of it as a small factory: you give it tool definitions, it normalizes them, builds a dependency graph, samples plausible endpoint chains, and writes **JSONL** you can score and compare.

You do **not** need a live API for tools—execution goes through a **mock engine** with schema-shaped outputs. Language models are optional: with no API keys, the stack runs in a **deterministic mock LLM** mode (great for CI and quick loops).

---

## What you get

- **Build**: `raw_tools.json` → normalized `registry.json` + a **NetworkX** tool graph.
- **Generate**: many conversations, each tied to an **intent** (trip planning, finance, etc.), a **chain plan**, and optional **steering** toggles.
- **Evaluate**: corpus metrics (entropy, unique chains, multi-tool ratio) plus **judge** scores on saved records.

---

## Requirements

- **Python 3.11+**

---

## Install

```bash
cd /path/to/MultiAgent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

---

## Environment (optional)

If you want real LLM calls (via LiteLLM), copy the example env and add keys:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` as needed. **If neither is set**, the project uses built-in mock responses for generation, judging, and repair—no bill, no network required for a basic run.

**Strict plan execution** (default on): the pipeline walks the planned endpoints in order with grounded args. To let the orchestrator drive tool choice more freely:

```bash
export SYNTH_STRICT_PLAN_EXECUTION=false
```

---

## Day-to-day commands

**1. Build artifacts** (run once after changing `data/raw_tools.json`)

```bash
synthetic-tooluse build --input data/raw_tools.json --artifact-dir artifacts/
```

This writes `artifacts/registry.json` and prints node/edge counts for the graph.

**2. Generate two comparable runs**

Run A turns **cross-conversation steering** off; Run B leaves it on (the CLI default).

```bash
# Run A — steering disabled
synthetic-tooluse generate \
  --artifact-dir artifacts/ \
  --num-samples 100 \
  --seed 42 \
  --output data/run_a.jsonl \
  --no-cross-conversation-steering

# Run B — steering enabled (default behavior)
synthetic-tooluse generate \
  --artifact-dir artifacts/ \
  --num-samples 100 \
  --seed 42 \
  --output data/run_b.jsonl \
  --cross-conversation-steering
```

Adjust `--num-samples`, `--seed`, and `--max-retries` if traces often fail validation and you want more attempts per conversation.

**3. Evaluate**

```bash
synthetic-tooluse evaluate --input data/run_a.jsonl --report reports/eval_run_a.json
synthetic-tooluse evaluate --input data/run_b.jsonl --report reports/eval_run_b.json
```

---

## Project layout (where things live)

| Area | Path |
|------|------|
| CLI entrypoint | `src/synthetic_tooluse/cli.py` |
| Normalize raw JSON | `src/synthetic_tooluse/registry/normalizer.py` |
| Graph construction | `src/synthetic_tooluse/graph/builder.py` |
| Intent definitions | `src/synthetic_tooluse/generation/intents.py` |
| Chain planning | `src/synthetic_tooluse/generation/chain_planner.py` |
| Main generation loop | `src/synthetic_tooluse/generation/pipeline.py` |
| Mock tool execution | `src/synthetic_tooluse/execution/mock_engine.py` |
| Agents (user, assistant, judge, repair) | `src/synthetic_tooluse/agents/` |

For a narrative tour, see **`walkthrough.md`**. For design rationale, see **`DESIGN.md`**.

**Architecture figures (SVG):** strict execution sequence and quality-gate state machine live under **`docs/images/`** (sources in **`docs/diagrams/`**). See **`docs/README.md`** to regenerate them, and **`docs/DIAGRAMS_EXPLAINED.md`** for a plain-language walkthrough of the diagrams.

**End-to-end implementation (detailed):** **`docs/END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md`** — full **STU-E2E** pipeline (build → generate → evaluate), internal mechanics, and what makes the design distinctive.

---

## Tests

```bash
pytest
```

---

## If the CLI isn’t found

Use the module form with `src` on the path:

```bash
PYTHONPATH=src python -m synthetic_tooluse.cli build --input data/raw_tools.json --artifact-dir artifacts/
```

Or ensure your virtualenv is activated after `pip install -e .`.
# MultiAgent_SAP
