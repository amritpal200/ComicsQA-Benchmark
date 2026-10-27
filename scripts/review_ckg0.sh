#!/usr/bin/env bash
# Review the existing audit; no annotation rescan or model inference.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/evidence/graph/review_ckg0.py" \
  --audit "$bench/reports/ckg0/v1" --core "$bench/core/v1" \
  --out "$bench/reports/ckg0/review_v1" "$@"
