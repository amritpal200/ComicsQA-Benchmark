#!/usr/bin/env bash
# CPU-only private candidate generation over completed CKG-1/2 artifacts.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/generation/build_gen1.py" \
  --graphs "$bench/evidence/ckg/v1" --visibility "$bench/evidence/name_visibility/v1" \
  --config "$repo/configs/tasks/gen1.json" --out "$bench/items/gen1/v1" "$@"
