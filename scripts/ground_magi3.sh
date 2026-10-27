#!/usr/bin/env bash
# Second MAGI v3 pass: ground Qwen panel captions and link phrases to human / MAGI v3 characters.
# Needs: annotations/human (scripts/export_human.sh), annotations/magi3, annotations/qwen32B.
# Usage: bash scripts/ground_magi3.sh --gpus 0,4 [run_grounding.py options]
#        CUDA_VISIBLE_DEVICES=0 bash scripts/ground_magi3.sh --device cuda --match "Naruto - 001" --limit 3
# Override paths with POPMANGA_IMAGES, HUMAN_OUT, MAGI3_OUT, QWEN_OUT, GROUNDING_OUT, MAGI3_MODEL.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
base="$storage/ComicsQA_Benchmark"
runner="$repo/src/comics_qa/annotations/magi3_grounding/run_grounding.py"
common=(--images "${POPMANGA_IMAGES:-$base/PopManga_Test/images}"
        --human "${HUMAN_OUT:-$base/annotations/human}"
        --magi3 "${MAGI3_OUT:-$base/annotations/magi3}"
        --qwen "${QWEN_OUT:-$base/annotations/qwen32B}"
        --out "${GROUNDING_OUT:-$base/annotations/magi3_grounding}"
        --model "${MAGI3_MODEL:-$storage/models/ocr/magiv3}")
out="${GROUNDING_OUT:-$base/annotations/magi3_grounding}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PYTHONUNBUFFERED=1

gpus=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus) gpus="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
run() { uv run --no-project --python 3.11 "$runner" "${common[@]}" "$@"; }
if [[ -z "$gpus" ]]; then
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
  sleep 20
done
status=0
for k in "${!pids[@]}"; do
  wait "${pids[$k]}" || { echo "shard $k exited with an error; see its log"; status=1; }
done
echo "all shards finished (status $status)"
exit $status
