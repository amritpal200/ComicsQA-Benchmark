#!/usr/bin/env bash
# Export PopManga human ground truth to one JSON per page (read-only source; CPU, ~1 min).
# Usage: bash scripts/export_human.sh [export_human.py options]
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
popmanga="${POPMANGA_ROOT:-$storage/ComicsQA_Benchmark/PopManga_Test}"
out="${HUMAN_OUT:-$storage/ComicsQA_Benchmark/annotations/human}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
exec uv run --no-project --python 3.11 "$repo/src/comics_qa/annotations/human/export_human.py" \
  --dataset "$popmanga/dataset" --images "$popmanga/images" --out "$out" "$@"
