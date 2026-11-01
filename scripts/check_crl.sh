#!/usr/bin/env bash
# CPU-only independent verification of one saved CRL result.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/crl/check_crl.py" \
  --graphs "$bench/evidence/ckg/v1" \
  --visibility "$bench/evidence/name_visibility/v1" "$@"
