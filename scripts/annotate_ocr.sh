#!/usr/bin/env bash
# OCR of every text box with PaddleOCR-VL-1.6 (human boxes; MAGI v3 boxes on pages without ground truth).
# Needs: annotations/human (scripts/export_human.sh), annotations/magi3, the model in models/ocr.
# Usage: bash scripts/annotate_ocr.sh --gpus 6,6,6,6 [run_ocr.py options]   (repeat an id = several processes on one GPU)
#        CUDA_VISIBLE_DEVICES=6 bash scripts/annotate_ocr.sh --device cuda --match "Naruto - 002" --limit 2
# Override paths with POPMANGA_IMAGES, HUMAN_OUT, MAGI3_OUT, OCR_OUT, OCR_MODEL.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
base="$storage/ComicsQA_Benchmark"
runner="$repo/src/comics_qa/annotations/ocr/run_ocr.py"
common=(--images "${POPMANGA_IMAGES:-$base/PopManga_Test/images}"
        --human "${HUMAN_OUT:-$base/annotations/human}"
        --magi3 "${MAGI3_OUT:-$base/annotations/magi3}"
        --out "${OCR_OUT:-$base/annotations/ocr_paddleocr_vl}"
        --model "${OCR_MODEL:-$storage/models/ocr/PaddleOCR-VL-1.6}")
out="${OCR_OUT:-$base/annotations/ocr_paddleocr_vl}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PYTHONUNBUFFERED=1
export HF_HOME="${HF_HOME:-$storage/.cache/hf_cache}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_VERBOSITY=error

gpus=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus) gpus="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
# GPUs older than sm_70 (e.g. TITAN Xp) need the CUDA 12.6 torch build: use the cu126 wrapper.
first_gpu="${gpus%%,*}"
first_gpu="${first_gpu:-${CUDA_VISIBLE_DEVICES:-0}}"
cap=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader -i "${first_gpu%%,*}" 2>/dev/null | tr -d ' ' || true)
if [[ -n "$cap" ]] && awk -v c="$cap" 'BEGIN{exit !(c < 7.0)}'; then
  runner="${runner%.py}_cu126.py"
  echo "GPU compute capability $cap < 7.0: using $(basename "$runner") (CUDA 12.6 torch, fp32)"
fi
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
  sleep 10
done
status=0
for k in "${!pids[@]}"; do
  wait "${pids[$k]}" || { echo "shard $k exited with an error; see its log"; status=1; }
done
echo "all shards finished (status $status)"
exit $status
