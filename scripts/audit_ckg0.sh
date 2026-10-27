#!/usr/bin/env bash
# Read-only CKG-0 audit. CPU / Python standard library; outputs never overwritten.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
exec python3 "$repo/src/comics_qa/evidence/graph/audit_ckg0.py" \
  --core "$bench/core/v1" --images "$bench/PopManga_Test/images" \
  --human "$bench/annotations/human" --magi3 "$bench/annotations/magi3" \
  --ocr "$bench/annotations/ocr_paddleocr_vl" \
  --out "$bench/reports/ckg0/v1" "$@"
