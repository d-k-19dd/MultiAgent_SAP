Skip to content
d-k-19dd
MultiAgent_SAP
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Wiki
Security and quality
Insights
Settings
Files
Go to file
t
MultiAgent
artifacts
data
docs
diagrams
images
DIAGRAMS_EXPLAINED.md
END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md
README.md
reports
src/synthetic_tooluse
agents
evaluation
execution
generation
graph
registry
schemas
__init__.py
cli.py
config.py
tests
DESIGN.md
README.md
pyproject.toml
requirements.txt
walkthrough.md
MultiAgent_SAP/MultiAgent/docs
/
END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md
in
main

Edit

Preview
Indent mode

Spaces
Indent size

2
Line wrap mode

Soft wrap
Editing END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md file contents
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
# Synthetic Tool-Use End-to-End Trace Implementation (STU-E2E)

**Official implementation name:** **Synthetic Tool-Use End-to-End Trace Implementation**  
**Short label used in this document:** **STU-E2E**

This document is the **single, detailed narrative** of how the entire system works—from a JSON file of tools to a JSONL dataset and an evaluation report. It is written for engineers and reviewers who want to understand **what runs, in what order, why it exists, and what makes it different** from “just prompt a model to write tool JSON.”

**Companion material**

- Visual sequence and quality gate: [DIAGRAMS_EXPLAINED.md](DIAGRAMS_EXPLAINED.md) and [images/](images/)
- Design rationale (shorter): [DESIGN.md](../DESIGN.md)
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
Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
No file chosen
Attach files by dragging & dropping, selecting or pasting them.
 
