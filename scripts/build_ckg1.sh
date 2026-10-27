#!/usr/bin/env bash
# CPU-only chapter graphs; source images/annotations are read-only.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/evidence/graph/build_ckg1.py" \
  --core "$bench/core/v1" --audit "$bench/reports/ckg0/v1" \
  --review "$bench/reports/ckg0/review_v1" --images "$bench/PopManga_Test/images" \
  --human "$bench/annotations/human" --magi3 "$bench/annotations/magi3" \
  --ocr "$bench/annotations/ocr_paddleocr_vl" \
  --out "$bench/evidence/ckg/v1" "$@"
