#!/usr/bin/env bash
# Run after GEN-2 v2 is complete; CPU only, no model calls.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/tasks/graph/verbalization/prepare_gen2.py" \
 --source "$bench/items/gen2/v2" --out "$bench/items/verb1/gen2_v2_requests" \
 --graphs "$bench/evidence/ckg/v1" --visibility "$bench/evidence/name_visibility/v1" \
 --rich "$bench/evidence/ckg3/v1" "$@"
