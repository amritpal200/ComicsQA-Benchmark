#!/usr/bin/env bash
# Qwen3-VL-32B panel + page captions for PopManga, using running server(s) from qwen_server.sh.
# Usage: bash scripts/annotate_qwen.sh --ports 18001,18002 [run_qwen.py options]
#   e.g. --concurrency 16 --page-workers 4      (concurrency is per server)
#        --check-only --limit 10                (read-only input check, no server needed)
# Override paths with POPMANGA_IMAGES, MAGI3_OUT, QWEN_OUT.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
project="$repo/src/comics_qa/annotations/qwen"
images="${POPMANGA_IMAGES:-$storage/ComicsQA_Benchmark/PopManga_Test/images}"
magi3="${MAGI3_OUT:-$storage/ComicsQA_Benchmark/annotations/magi3}"
out="${QWEN_OUT:-$storage/ComicsQA_Benchmark/annotations/qwen32B}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export UV_PROJECT_ENVIRONMENT="${QWEN_ENV:-$storage/.cache/qwen_annotations/venv-$(hostname -s)}"
export PYTHONUNBUFFERED=1

ports="18001"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ports|--port) ports="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
urls=()
IFS=, read -ra list <<< "$ports"
for p in "${list[@]}"; do urls+=(--base-url "http://127.0.0.1:$p"); done

cd "$project"
# --inexact: do not remove the server's vLLM packages from the shared environment.
exec uv run --frozen --inexact python run_qwen.py --images "$images" --magi3 "$magi3" --out "$out" \
  "${urls[@]}" "${args[@]}"
