#!/usr/bin/env bash
# CPU-only richer evidence and visual-review queues; no GPU inference.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/evidence/graph/rich/build.py" \
  --graphs "$bench/evidence/ckg/v1" --visibility "$bench/evidence/name_visibility/v1" \
  --out "$bench/evidence/ckg3/v1" "$@"
