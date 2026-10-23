#!/usr/bin/env bash
# Run one pipeline command.
# Usage: bash scripts/run.sh <command> [--gpu N | --gpus N,M,...] [command options...]
#   --gpu N        one GPU
#   --gpus 2,3,4,5 data-parallel training on several GPUs (train-* commands only; torchrun)
# Commands: verify-weights, prepare-coco, prepare-manga, train-without-text,
#           train-add-text, train-depth, predict, evaluate, test
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

[[ $# -ge 1 ]] || { sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 2; }
cmd="$1"; shift
gpus=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu) export CUDA_VISIBLE_DEVICES="$2"; shift 2 ;;
    --gpus) gpus="$2"; export CUDA_VISIBLE_DEVICES="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done

[[ -x "$CD_ENV/bin/python" ]] || { echo "Missing environment $CD_ENV; run: bash scripts/setup_env.sh" >&2; exit 1; }

if [[ "$cmd" == test ]]; then
  export CUDA_VISIBLE_DEVICES=""
  exec "$CD_ENV/bin/python" -m unittest discover -s "$CD_REPO/tests" -t "$CD_REPO" "${args[@]}"
fi

if [[ -n "$gpus" && "$gpus" == *,* ]]; then
  [[ "$cmd" == train-* ]] || { echo "--gpus with several GPUs is only for train-* commands" >&2; exit 2; }
  IFS=, read -ra ids <<< "$gpus"
  exec "$CD_ENV/bin/torchrun" --standalone --nproc_per_node="${#ids[@]}" \
    -m comics_depth "$cmd" "${args[@]}"
fi
exec "$CD_ENV/bin/python" -m comics_depth "$cmd" "${args[@]}"
