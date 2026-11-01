#!/usr/bin/env bash
# CPU request preparation only; no Qwen inference.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/verbalization/prepare.py" \
  --source "$bench/items/gen1/v1" --out "$bench/items/verb1/v1_requests" "$@"
