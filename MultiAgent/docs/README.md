# Architecture diagrams

**Human-readable walkthrough** of what the figures mean (strict execution + quality gate): **[DIAGRAMS_EXPLAINED.md](DIAGRAMS_EXPLAINED.md)**.

**Full end-to-end implementation narrative** (official name **STU-E2E**, build → generate → evaluate, internals, uniqueness): **[END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md](END_TO_END_SYNTHETIC_TOOLUSE_TRACE_IMPLEMENTATION.md)**.

Rendered **SVG images** (for READMEs, decks, or recruiters who do not run Mermaid):

| Diagram | Image | Source (Mermaid) |
|--------|-------|------------------|
| Strict plan execution — one trace | [images/strict-plan-sequence.svg](images/strict-plan-sequence.svg) | [diagrams/strict-plan-sequence.mmd](diagrams/strict-plan-sequence.mmd) |
| Per-sample quality gate — retries & accept | [images/quality-gate-statemachine.svg](images/quality-gate-statemachine.svg) | [diagrams/quality-gate-statemachine.mmd](diagrams/quality-gate-statemachine.mmd) |

**Regenerate SVGs** (requires Node / npm). Charts use a **black-and-white** theme (`diagrams/mermaid-theme-bw.json`), a **white** background, and a short **post-pass** so actor boxes and grays become pure `#000` / `#fff` (Mermaid still inlines some grays otherwise).

From repo root:

```bash
./docs/diagrams/render-bw.sh
```

Or manually:

```bash
cd docs
npx --yes @mermaid-js/mermaid-cli@11 -i diagrams/strict-plan-sequence.mmd -o images/strict-plan-sequence.svg -c diagrams/mermaid-theme-bw.json -b white
npx --yes @mermaid-js/mermaid-cli@11 -i diagrams/quality-gate-statemachine.mmd -o images/quality-gate-statemachine.svg -c diagrams/mermaid-theme-bw.json -b white
# optional: same perl substitutions as in render-bw.sh for strict monochrome
```

GitHub also renders `.mmd` content if pasted into a Markdown fenced block as `mermaid`; the `.mmd` files here are plain sources for edits and CI.
