#!/usr/bin/env bash
# Regenerate SVGs with black/white theme + normalize Mermaid grays to #000/#fff.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
CLI=(npx --yes @mermaid-js/mermaid-cli@11)
"${CLI[@]}" -i docs/diagrams/strict-plan-sequence.mmd -o docs/images/strict-plan-sequence.svg \
  -c docs/diagrams/mermaid-theme-bw.json -b white
"${CLI[@]}" -i docs/diagrams/quality-gate-statemachine.mmd -o docs/images/quality-gate-statemachine.svg \
  -c docs/diagrams/mermaid-theme-bw.json -b white
for f in docs/images/strict-plan-sequence.svg docs/images/quality-gate-statemachine.svg; do
  perl -i -pe 's/#eaeaea/#ffffff/g; s/#f4f4f4/#ffffff/g; s/#eeeeee/#ffffff/gi; s/#eee\b/#ffffff/g; s/#cccccc/#000000/gi; s/#999999/#000000/g; s/#999\b/#000000/g; s/#666666/#000000/g; s/#666\b/#000000/g; s/#333333/#000000/g; s/#333\b/#000000/g; s/#552222/#000000/g; s/rgba\(185,185,185,1\)/rgba(0,0,0,0.15)/g' "$f"
done
echo "Wrote docs/images/*.svg (black & white)."
