#!/usr/bin/env bash
# Build the benchmark foundation (chapters, pages, character identities) from human GT + MAGI v3.
# CPU only, about a minute. Output: $BENCH/core/<version> (never overwritten).
# Usage: bash scripts/build_core.sh [--version v2]
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/core/build_core.py" \
  --images "$bench/PopManga_Test/images" --human "$bench/annotations/human" \
  --magi3 "$bench/annotations/magi3" --out "$bench/core" "$@"
