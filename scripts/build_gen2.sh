#!/usr/bin/env bash
# CPU-only proof-backed OCR/lexical anchored candidate generation.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/gen2/build.py" \
  --graphs "$bench/evidence/ckg/v1" --visibility "$bench/evidence/name_visibility/v1" \
  --rich "$bench/evidence/ckg3/v1" --config "$repo/configs/tasks/gen2_v2.json" \
  --out "$bench/items/gen2/v2" "$@"
