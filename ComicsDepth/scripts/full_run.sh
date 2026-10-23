#!/usr/bin/env bash
# Full ComicsDepth pipeline: prepare data, then the three training stages, then evaluation.
# Resumable: rerun the same command; finished preparations/stages are skipped and training
# continues from the last completed epoch.
# Usage: bash scripts/full_run.sh [GPUS] [WORKERS_PER_GPU] [CONFIG]
#   defaults: 2,3,4,5  8  configs/default.toml      (e.g. configs/fast512.toml)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
gpus="${1:-2,3,4,5}"
workers="${2:-8}"
config="${3:-configs/default.toml}"
first_gpu="${gpus%%,*}"
c=(--config "$config")

echo "[$(date)] start: GPUs $gpus, $workers loader workers per GPU, config $config"
bash scripts/run.sh prepare-manga "${c[@]}" --num-workers "$workers"
bash scripts/run.sh prepare-coco "${c[@]}" --gpu "$first_gpu"
for stage in train-without-text train-add-text train-depth; do
  echo "[$(date)] $stage"
  bash scripts/run.sh "$stage" "${c[@]}" --gpus "$gpus" --set train.num_workers="$workers"
done
out=/data/151-3/comics/ComicsDepth/evaluation/$(basename "$config" .toml)
if [[ ! -e "$out" ]]; then
  echo "[$(date)] evaluate"
  bash scripts/run.sh evaluate "${c[@]}" --gpu "$first_gpu" \
    --models midas comicsdepth depth_anything_v2 --output "$out"
fi
echo "[$(date)] all done"
