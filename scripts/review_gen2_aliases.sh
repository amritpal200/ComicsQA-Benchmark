#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/gen2/review_aliases.py" \
 --graphs "$bench/evidence/ckg/v1" --visibility "$bench/evidence/name_visibility/v1" "$@"
