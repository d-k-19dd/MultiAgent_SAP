# Synthetic Tool-Use End-to-End Trace Implementation (STU-E2E)

**Official implementation name:** **Synthetic Tool-Use End-to-End Trace Implementation**  
**Short label used in this document:** **STU-E2E**

This document is the **single, detailed narrative** of how the entire system works—from a JSON file of tools to a JSONL dataset and an evaluation report. It is written for engineers and reviewers who want to understand **what runs, in what order, why it exists, and what makes it different** from “just prompt a model to write tool JSON.”

**Companion material**

- Visual sequence and quality gate: [DIAGRAMS_EXPLAINED.md](DIAGRAMS_EXPLAINED.md) and [images/](images/)
- Repo usage: [README.md](../README.md)

---

## 1. What STU-E2E is trying to solve

Real tool-using assistants must:

1. **Choose the right API** among many similar names.  
2. **Order calls** so outputs exist before dependent inputs (e.g. search before book).  
3. **Ground arguments** in prior results (IDs, dates, locations).  
4. **Speak naturally** without contradicting what tools already returned.

If you ask one LLM to “invent a multi-tool conversation,” it often:

- Hallucinates IDs or skips prerequisite calls.  
- Repeats the same call with the same arguments.  
- Drifts into unrelated domains.

**STU-E2E** treats tool use as a **systems problem first** and a **language problem second**:

- **Systems layer:** normalize tools, build a **directed graph** of endpoints, **plan** an ordered chain under **intent constraints**, **execute** calls through a **mock engine** that returns structured-ish payloads, and **thread state** between steps.  
- **Language layer:** user simulator and assistant (and optionally repair/judge models) dress that skeleton as a believable chat.  
- **Quality layer:** validators and judges decide whether a trace is allowed into the dataset, with **retries** when it is not.

That split is the core idea of the implementation.

---

## 2. The three phases you actually run

Everything is exposed through one CLI (`src/synthetic_tooluse/cli.py`):

| Phase | Command | Primary outputs |
|--------|---------|------------------|
| **A. Ingest & compile** | `synthetic-tooluse build …` | `artifacts/registry.json` (and an in-memory graph at build time—see note below) |
| **B. Generate traces** | `synthetic-tooluse generate …` | `data/*.jsonl` (one `ConversationRecord` per line) |
| **C. Evaluate corpus** | `synthetic-tooluse evaluate …` | `reports/*.json` (aggregate metrics + judge means) |

**Note on the graph:** `build` prints node/edge counts but does not persist the graph to disk by default; `generate` **reloads** `registry.json`, runs `GraphBuilder` again, and then runs `GenerationPipeline`. So the “source of truth” artifact between phases is the **registry**; the graph is **reproducibly derived** from it.

---

## 3. Phase A — Build: from messy JSON to a typed corpus

### 3.1 Entry point

`build` reads `data/raw_tools.json` (or another path you pass). If the file is missing, the CLI can materialize a **tiny hotel fixture** so the pipeline is still demonstrable—useful for CI and first-time clones.

### 3.2 What happens internally: `RegistryNormalizer`

**File:** `src/synthetic_tooluse/registry/normalizer.py`

Raw tool corpora rarely agree on field names. The normalizer:

- Accepts several shapes: `endpoints` vs `api_list`, `parameters` vs `inputs`, `response` vs `returns`, optional `response_schema`.  
- Produces strict **`ToolDefinition`** objects with nested **`EndpointDescriptor`** records: parameters get **`ParamType`** and a coarse **`SemanticRole`** (identifier, location, date range, free text, etc.) from **name heuristics**, not from an LLM.  
- Builds a **`ResponseSchema`** so later graph code can ask “what kinds of entities does this endpoint claim to produce?”

**Why this matters:** every later stage trusts **Pydantic** types. You are not regex-parsing JSON inside the planner or the mock engine; you are reading validated objects.

### 3.3 What happens internally: `GraphBuilder`

**File:** `src/synthetic_tooluse/graph/builder.py`

Each **endpoint** becomes a **node** on a **NetworkX** `DiGraph`. Node attributes include `tool_id`, `domain`, `description`, **required input names**, and **inferred produced entity types** from the response schema.

Edges are added with typed **`RelationType`** labels and weights:

- **SAME_TOOL** — weak links between endpoints of one tool (exploration within a product).  
- **SAME_DOMAIN** — medium links within a business domain (Travel, Finance, …).  
- **OUTPUT_TO_INPUT_COMPATIBLE** — stronger links when something the upstream response “looks like” (e.g. `hotel_id`) appears in downstream **required** parameter names—this is a **deliberately heuristic** stand-in for a full semantic mapper.

**Why this matters:** the graph is not decoration. It is the **space of plausible transitions** the chain planner walks when there is no perfect template, and it biases the random walk toward **data-compatible** hops.

### 3.4 Artifact written

`artifacts/registry.json` — a JSON list of `ToolDefinition.model_dump()` entries. This file is what **generate** consumes.

---

## 4. Phase B — Generate: one conversation at a time

### 4.1 Entry point

`generate`:

1. Loads `registry.json` into `ToolDefinition` instances.  
2. Rebuilds the graph with `GraphBuilder`.  
3. Constructs `GenerationPipeline(registry, graph, steering_enabled=…)`.  
4. Seeds Python’s `random` from `--seed` for reproducible sampling.  
5. Passes `ChainConstraints(min_num_distinct_tools=2)` as a baseline object that the pipeline **mutates per sample** (intent fields, multi-tool flag, etc.).  
6. Calls `pipeline.run_generation(count, constraints, max_retries)` and writes **JSONL**.

### 4.2 Outer loop: corpus pacing and retries

**File:** `src/synthetic_tooluse/generation/pipeline.py`

For each sample index `i`:

1. **Multi-tool ratio feedback** — The pipeline tracks how many accepted traces so far had “strong multi-tool” behavior (≥3 calls and ≥2 distinct tools). While the running ratio is **below 0.60** and the registry is rich enough, it sets `constraints.require_multi_tool = True`; otherwise it relaxes that flag. This is a **dataset-level throttle**, not a per-message LLM hint: it directly changes what the **planner** is asked to produce.

2. **Inner retry loop** — Up to `max(3, max_retries)` attempts **per sample**. If a trace is rejected (e.g. zero tool calls, low diversity tag), the pipeline **does not** append a bad row; it **continues** the inner loop with a fresh intent roll. If all inner attempts fail, it logs an error for that sample index and moves on.

### 4.3 Intent binding: what “scenario” means here

Each attempt picks a **`ScenarioIntent`** from `INTENT_CONFIGS` (`src/synthetic_tooluse/generation/intents.py`):

- Human-readable **name** and **description** (what the user supposedly wants).  
- **Primary domains** — restrict which parts of the graph are even in play for planning.  
- **Positive / negative keywords** — steer semantic filtering in the planner and later catch obvious mismatches in validation.

Those fields are copied onto **`ChainConstraints`**, which is what **`ChainSampler`** / **`chain_planner`** read.

**Internal effect:** before any “creative” agent runs, the system has already declared: *this trace is a budgeting story, not a lyrics search.*

### 4.4 Planning: how the ordered tool list is born

**Files:** `src/synthetic_tooluse/graph/sampler.py`, `src/synthetic_tooluse/generation/chain_planner.py`

The sampler is a thin wrapper. The planner:

1. If the intent string matches a **curated template list** (`PREDEFINED_CHAINS`), it may take a **known-good multi-step path** for that vertical (e.g. trip planning chains that already mix flights, hotels, itinerary).  
2. Otherwise it gathers **candidate graph nodes** filtered by domain and keyword rules (with a **lenient retry** that drops negative-keyword filtering if nothing survives—so generation does not deadlock on aggressive keywords).  
3. Chooses a **walk length** (with guards so tiny graphs never ask `randint` for an empty range).  
4. Performs a **weighted random walk** where successors are scored using edge **`RelationType`** weights and an optional bias toward **distinct tools** when multi-tool pacing is on.

If multi-tool is required but the walk is too thin, the planner can **upgrade** to a predefined template when one exists.

**Output:** a **`ChainPlan`**: an ordered list of **`ChainStep`** objects (endpoint id, purpose string, required slot names, optional clarification flag).

**Internal uniqueness:** the plan is **structural**. The LLM is not inventing the backbone ordering from whole cloth in strict mode; it is executing or narrating a **committed skeleton**.

### 4.5 Simulation: strict vs orchestrated paths

The pipeline branches on **`STRICT_PLAN_EXECUTION`** (`src/synthetic_tooluse/config.py`, env `SYNTH_STRICT_PLAN_EXECUTION`, default **on**).

#### Strict mode (default): “execute the plan, do not improvise tools”

For each `ChainStep`:

1. **`build_arguments_for_endpoint`** (`generation/arg_resolution.py`) builds a dict:  
   - Pulls from **`ContextManager.state`** and **`SessionState.extracted_slots`** when names match.  
   - Fills required holes from safe defaults or latest known IDs.  
   - Applies endpoint-specific hygiene (e.g. strip bogus `hotel_id` from `search_hotels` city field).

2. **`stable_tool_signature`** + **`may_execute_tool`** (`generation/execution_dedupe.py`) decide whether this exact `(endpoint, args)` was already executed. If yes, the step is **skipped** unless the plan marked the step **`retryable`** (rare second pass on same endpoint with a reason).

3. The pipeline appends an **assistant** message with **OpenAI-style** `tool_calls` (function name derived from endpoint id, arguments JSON).

4. **`MockExecutionEngine.execute`** runs the call:  
   - It is the **source of truth** for return payloads (not the assistant).  
   - It updates **`SessionState`** entity maps / slots as side effects.

5. **`ContextManager.extract_from_output`** parses the string output into key/value context for the **next** argument resolution.

6. A **tool** role message is appended with the string output.

There is **no** per-step LLM call for “what tool next?” in this branch—the plan already decided. The assistant reappears at the **end** for `finalize=True` to optionally emit a closing natural-language answer that fits the transcript.

#### Non-strict mode: “assistant in the loop each step”

Same plan exists, but each step:

- Builds a **system context string** from `ContextManager`.  
- Calls **`AssistantOrchestrator.generate_turn`** with `forced_arguments` as a guardrail.  
- Allows a bounded **clarification** ping-pong with **`UserSimulator.generate_reply`**.  
- If the model emits multiple tool calls for one step, the pipeline **collapses** to a single planned endpoint.

**Internal trade-off:** more naturalism and model agency; **less** guarantee that the transcript matches the plan or that arguments stay clean—hence stricter validation pressure.

### 4.6 Packaging: from raw history to `ConversationRecord`

The pipeline converts the internal `history` list into typed **`Message`** models, preserving **real endpoint ids** on `ToolCallRequest` using `real_endpoint_map` (because function names in messages are sanitized shortened strings).

It then constructs **`ConversationRecord`** with rich **metadata**: endpoints used, distinct tool counts, planned vs executed steps, duplicate skip count, strict flag, intent name, domains, workflow template, steering flag, model id, etc.

**`analyze_record_quality`** (`evaluation/trace_analyzer.py`) adds lightweight derived signals into metadata for downstream evaluation.

### 4.7 Quality gates before a row is “accepted”

Still inside the inner retry, **after** a candidate record exists:

1. **`TraceValidator.validate`** — deterministic rules: zero tools, duplicate identical calls in transcript, domain/intent mismatches, weak chains vs plan, hallucinated IDs not present in session, etc.  
   - If invalid: tag failures, set `rejection_reason`, call **`RepairAgent.attempt_repair`** with the validator message. The repair agent may rewrite messages; this is an **LLM edit pass** (or mock) guided by failure tags.

2. **`JudgeAgent.evaluate`** — rubric scores (naturalness, tool correctness, task completion, grounding coherence) plus failure tags.  
   - If mean score `< 4.0`: extend failure tags, call **repair again** with judge context.

3. **`SteeringManager.update_stats`** — records domains, per-endpoint counts, and a simple chain hash string for future diversity hooks (weights returned to the sampler are still a **stub**, but telemetry is real).

4. **Hard rejects** — If after all that there are still **zero** tool calls, or a **`low_diversity`** failure tag, the attempt is **discarded** and the inner loop retries with a new roll.

5. **Accept** — On success, `rejection_reason` is cleared and the record is appended to the in-memory results list, which the CLI writes as **one JSON line**.

**Internal uniqueness:** you are looking at a **generation pipeline with an embedded QA loop**, not a single forward pass.

---

## 5. Phase C — Evaluate: corpus-level view

**File:** `src/synthetic_tooluse/cli.py` (`evaluate` command)

1. Reads every line of JSONL into **`ConversationRecord`**.  
2. **`compute_corpus_metrics`** (`evaluation/metrics.py`) on metadata: **endpoint entropy**, **unique chain ratio** (distinct endpoint sequences / total).  
3. Averages **judge** dimensions across records.  
4. Computes **multi_tool_ratio** (share of traces with ≥3 calls and ≥2 distinct tools) and **distinct_tools_ge2_ratio**.  
5. **`aggregate_corpus_signals`** adds extra corpus-level summaries.  
6. Writes one JSON report.

**Why this matters:** you can compare two generation runs (e.g. steering on vs off) with **numbers**, not vibes.

---

## 6. What is genuinely unique about STU-E2E

This section is the “why should anyone care” list—grounded in what the code actually does.

1. **Plan-first, execute-second (strict mode)**  
   Many demos interleave “think” and “call tools” in one model stream. Here, **the plan is an object** (`ChainPlan`) and strict mode **executes it** with resolved arguments and a mock engine. That is closer to **orchestrated workflows** than to unstructured chat.

2. **Mock execution owns tool truth**  
   The assistant does not author tool JSON results. **`MockExecutionEngine`** returns outputs and updates **session entities**. That prevents a whole class of “the model confabulated a happy JSON” bugs.

3. **Referential threading without a vector DB**  
   **`SessionState`** + **`ContextManager`** implement **within-trace** memory with deterministic IDs and parsed slots. For synthetic dataset construction, that is simpler and more auditable than semantic retrieval for every ID.

4. **Graph-informed diversity under constraints**  
   The tool graph is built from **schema heuristics** (output entity hints vs required inputs). Random walks are **biased** by edge semantics, not uniform over all tools.

5. **Intent as a first-class constraint object**  
   Intents are not just a string prefix in a prompt; they populate **`ChainConstraints`** that affect **planning** and **validation**.

6. **Dedupe by signature**  
   Identical `(endpoint, arguments)` repeats are suppressed unless explicitly **retryable**, improving dataset hygiene.

7. **Validator → repair → judge → repair loop**  
   Structural checks and subjective scores both feed **repair**, and catastrophic traces are **thrown away** with retries.

8. **Offline-first operation**  
   With no API keys, **`USE_MOCK_LLM`** paths still let you run **build → generate → evaluate** for development and tests.

---

## 7. Internal data contracts (mental map)

| Contract | Role |
|----------|------|
| `ToolDefinition` / `EndpointDescriptor` | What tools exist and what each endpoint expects/returns. |
| `ChainConstraints` | Per-sample knobs: intent, keywords, domains, multi-tool requirement, etc. |
| `ChainPlan` / `ChainStep` | Ordered execution intent for the trace. |
| `SessionState` | Ground truth for IDs and slots during execution. |
| `ContextManager` | Parsed view of recent tool outputs for argument filling. |
| `ConversationRecord` | Serializable trace + metadata for JSONL and evaluation. |

---

## 8. Configuration levers worth knowing

| Lever | Effect |
|--------|--------|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Present → real LLM calls via LiteLLM; absent → mock agents. |
| `SYNTH_STRICT_PLAN_EXECUTION` | `true` (default) → strict executor path; `false` → orchestrator-in-the-loop path. |
| `--cross-conversation-steering` / `--no-cross-conversation-steering` | Enables `SteeringManager` bookkeeping across samples. |
| `--seed` | Reproducible Python `random` sampling for plans and intents. |
| `--max-retries` | Widens inner retry attempts per sample when validation is picky. |

---

## 9. Where to read the code (map)

| Concern | Location |
|---------|-----------|
| CLI orchestration | `src/synthetic_tooluse/cli.py` |
| Normalization | `src/synthetic_tooluse/registry/normalizer.py` |
| Graph | `src/synthetic_tooluse/graph/builder.py` |
| Intents | `src/synthetic_tooluse/generation/intents.py` |
| Planning | `src/synthetic_tooluse/generation/chain_planner.py` |
| Generation & QA loop | `src/synthetic_tooluse/generation/pipeline.py` |
| Mock APIs | `src/synthetic_tooluse/execution/mock_engine.py` |
| State | `src/synthetic_tooluse/execution/state.py` |
| Validation | `src/synthetic_tooluse/generation/validator.py` |
| Agents | `src/synthetic_tooluse/agents/` |
| Corpus metrics | `src/synthetic_tooluse/evaluation/metrics.py` |

---

## 10. Closing mental model

**STU-E2E** is best understood as a **compiler + runtime + test harness** for conversations:

- **Compile:** raw tools → typed registry + graph.  
- **Runtime:** intents + constraints → plan → (strict) execute with grounded args and mock IO → language finish.  
- **Test harness:** analyze → validate → judge → repair or reject → JSONL.

For output files you can look at data/run_a.json and data/run_b.json
for ecaluation metrics you can find under the src/reports for each reach run


That is the full end-to-end implementation this repository ships—by design.
