#!/usr/bin/env bash
# User-submitted CPU request worker. No GPU allocation/server launch is assumed.
# Supply account/partition/time/array resources explicitly in your sbatch command.
set -euo pipefail
: "${BENCHMARK1000_CODE:?Set the Code directory on MN5}"
: "${BENCHMARK1000_REQUESTS:?Set the preflighted request store}"
: "${BENCHMARK1000_RUNS:?Set a new run root}"
: "${BENCHMARK1000_SHARDS:?Set the number of worker shards}"
: "${BENCHMARK1000_PYTHON:?Set an existing suitable Python environment}"
worker_index="${SLURM_ARRAY_TASK_ID:-0}"
cd "$BENCHMARK1000_CODE"
bash scripts/benchmark1000.sh run-qwen \
  --requests "$BENCHMARK1000_REQUESTS" \
  --shard-index "$worker_index" --shards "$BENCHMARK1000_SHARDS" \
  --max-requests "${BENCHMARK1000_MAX_REQUESTS:-2}" \
  --out "$BENCHMARK1000_RUNS/shard_$worker_index"
