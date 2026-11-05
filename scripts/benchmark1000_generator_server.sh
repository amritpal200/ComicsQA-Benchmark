#!/usr/bin/env bash
# Local free-generation model server (expansion plan X4): Qwen3-VL-32B on one local GPU, OpenAI-compatible, 32k context.
# Reuses the locked Qwen annotation environment (vLLM 0.11.2). Keep it running in its own screen.
# Usage: bash scripts/benchmark1000_generator_server.sh --gpu 0 [--port 18201] [--mem 0.6] [--thinking]
#   default model: Qwen/Qwen3-VL-32B-Instruct-FP8 (cached); --thinking: /data/151-3/comics/models/Qwen3-VL-32B-Thinking
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export UV_PROJECT_ENVIRONMENT="${QWEN_ENV:-$storage/.cache/qwen_annotations/venv-$(hostname -s)}"
export HF_HOME="${HF_HOME:-$storage/.cache/hf_cache}"
export HF_HUB_OFFLINE=1
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$storage/.cache/freegen/vllm}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$storage/.cache/freegen/triton}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$storage/.cache/freegen/xdg}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
gpu=""; port=18201; mem=0.6; model="Qwen/Qwen3-VL-32B-Instruct-FP8"; served="qwen3-vl-32b-instruct-fp8"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu) gpu="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --mem) mem="$2"; shift 2 ;;
    --thinking) model="$storage/models/Qwen3-VL-32B-Thinking"; served="qwen3-vl-32b-thinking"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[[ -n "$gpu" ]] || { sed -n '2,5p' "${BASH_SOURCE[0]}"; exit 2; }
cd "$repo/src/comics_qa/annotations/qwen"
uv sync --frozen --group server
CUDA_VISIBLE_DEVICES="$gpu" OMP_NUM_THREADS=1 exec uv run --frozen --group server vllm serve "$model" \
  --served-model-name "$served" --host 127.0.0.1 --port "$port" --max-model-len 32768 --max-num-seqs 4 \
  --gpu-memory-utilization "$mem" --limit-mm-per-prompt '{"image": 0, "video": 0}' --enable-chunked-prefill
