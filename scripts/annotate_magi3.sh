#!/usr/bin/env bash
# MAGI v3 annotations for the PopManga images (read-only input, separate output folder).
# Usage: bash scripts/annotate_magi3.sh --gpus 0,2,4,5 [run_magi3.py options]
#        bash scripts/annotate_magi3.sh --cpu --limit 2 --num-beams 1 --max-new-tokens 64   (smoke)
# One process per GPU, each on its own shard (K/N) of the pending pages; logs per shard.
# Override paths with POPMANGA_IMAGES, MAGI3_OUT, MAGI3_MODEL.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
images="${POPMANGA_IMAGES:-$storage/ComicsQA_Benchmark/PopManga_Test/images}"
out="${MAGI3_OUT:-$storage/ComicsQA_Benchmark/annotations/magi3}"
model="${MAGI3_MODEL:-$storage/models/ocr/magiv3}"
runner="$repo/src/comics_qa/annotations/magi3/run_magi3.py"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export HF_HOME="${HF_HOME:-$storage/.cache/hf_cache}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PYTHONUNBUFFERED=1

gpus=""
cpu=0
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus) gpus="$2"; shift 2 ;;
    --cpu) cpu=1; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
common=(--images "$images" --out "$out" --model "$model")
run() { uv run --no-project --python 3.11 "$runner" "${common[@]}" "$@"; }

if [[ $cpu == 1 || -z "$gpus" ]]; then
  [[ $cpu == 1 ]] && export CUDA_VISIBLE_DEVICES="" && args+=(--device cpu)
  run "${args[@]}"
  exit $?
fi

IFS=, read -ra ids <<< "$gpus"
n=${#ids[@]}
mkdir -p "$out/logs"
stamp=$(date +%Y%m%d_%H%M%S)
pids=()
for k in "${!ids[@]}"; do
  log="$out/logs/${stamp}_shard${k}of${n}_gpu${ids[$k]}.log"
  echo "shard $k/$n on GPU ${ids[$k]} -> $log"
  CUDA_VISIBLE_DEVICES="${ids[$k]}" run --device cuda --shard "$k/$n" "${args[@]}" > "$log" 2>&1 &
  pids+=($!)
  sleep 20   # stagger model loading
done
status=0
for k in "${!pids[@]}"; do
  if ! wait "${pids[$k]}"; then
    echo "shard $k exited with an error; see its log"; status=1
  fi
done
echo "all shards finished (status $status)"
exit $status
