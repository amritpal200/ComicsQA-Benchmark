#!/usr/bin/env bash
# Independent event-fact verifier (improvement plan S5): an OpenAI-compatible vLLM server for a non-Qwen VLM.
# Reuses the locked Qwen annotation environment (vLLM 0.11.2). Keep it running in its own screen.
# Usage: bash scripts/benchmark1000_event_verifier.sh --download                 (once: fetch the model, ~30 GB)
#        bash scripts/benchmark1000_event_verifier.sh --gpu 2 [--port 18101] [--mem 0.45]
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
model_id="${VERIFIER_MODEL_ID:-OpenGVLab/InternVL3-14B}"
model_dir="${VERIFIER_MODEL_DIR:-$storage/models/$(basename "$model_id")}"
served="${VERIFIER_SERVED_NAME:-$(basename "$model_id" | tr '[:upper:]' '[:lower:]')}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export UV_PROJECT_ENVIRONMENT="${QWEN_ENV:-$storage/.cache/qwen_annotations/venv-$(hostname -s)}"
export HF_HOME="${HF_HOME:-$storage/.cache/hf_cache}"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$storage/.cache/event_verifier/vllm}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$storage/.cache/event_verifier/triton}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$storage/.cache/event_verifier/xdg}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID

gpu=""; port=18101; mem=0.45; download=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu) gpu="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --mem) mem="$2"; shift 2 ;;
    --download) download=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
cd "$repo/src/comics_qa/annotations/qwen"
uv sync --frozen --group server
if [[ $download == 1 ]]; then
  HF_HUB_OFFLINE=0 uv run --frozen --group server python -c \
    "from huggingface_hub import snapshot_download; print(snapshot_download('$model_id', local_dir='$model_dir'))"
  exit 0
fi
[[ -n "$gpu" ]] || { sed -n '2,5p' "${BASH_SOURCE[0]}"; exit 2; }
[[ -d "$model_dir" ]] || { echo "Model not found: $model_dir (run with --download first)" >&2; exit 1; }
export HF_HUB_OFFLINE=1
CUDA_VISIBLE_DEVICES="$gpu" exec uv run --frozen --group server vllm serve "$model_dir" \
  --served-model-name "$served" --trust-remote-code --port "$port" --max-model-len 8192 \
  --limit-mm-per-prompt '{"image": 1}' --gpu-memory-utilization "$mem" --max-num-seqs 32
