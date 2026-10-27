#!/usr/bin/env bash
# Start Qwen3-VL-32B vLLM server(s) for caption annotation. Keep this running in its own screen.
# Usage: bash scripts/qwen_server.sh --gpus 2,5 [--port 18001] [serve.py options]
#   one server per GPU, on ports PORT, PORT+1, ...; e.g. --profile 46gb --max-num-seqs 16
#   bash scripts/qwen_server.sh --gpus 2 --profile 46gb --max-num-seqs 16 --print-only   (show command)
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage="${CD_STORAGE:-/data/151-3/comics}"
project="$repo/src/comics_qa/annotations/qwen"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$storage/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$storage/.cache/uv_cache/python}"
export UV_PROJECT_ENVIRONMENT="${QWEN_ENV:-$storage/.cache/qwen_annotations/venv-$(hostname -s)}"
export HF_HOME="${HF_HOME:-$storage/.cache/hf_cache}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$storage/.cache/qwen_annotations/vllm}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$storage/.cache/qwen_annotations/triton}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$storage/.cache/qwen_annotations/xdg}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID

gpus=""
port=18001
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus|--gpu) gpus="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
[[ -n "$gpus" ]] || { sed -n '2,5p' "${BASH_SOURCE[0]}"; exit 2; }
cd "$project"
uv sync --frozen --group server   # environment from the copied uv.lock (vLLM 0.11.2)

IFS=, read -ra ids <<< "$gpus"
if [[ ${#ids[@]} == 1 ]]; then
  CUDA_VISIBLE_DEVICES="${ids[0]}" exec uv run --frozen --group server python serve.py --port "$port" "${args[@]}"
fi
logs="$storage/ComicsQA_Benchmark/annotations/qwen32B_server_logs"
mkdir -p "$logs"
pids=()
for k in "${!ids[@]}"; do
  p=$((port + k))
  log="$logs/$(date +%Y%m%d_%H%M%S)_gpu${ids[$k]}_port${p}.log"
  echo "server on GPU ${ids[$k]}, port $p -> $log"
  CUDA_VISIBLE_DEVICES="${ids[$k]}" uv run --frozen --group server python serve.py --port "$p" "${args[@]}" \
    > "$log" 2>&1 &
  pids+=($!)
done
trap 'kill "${pids[@]}" 2>/dev/null' INT TERM EXIT
echo "Servers starting; wait until each log shows 'Application startup complete'. Ctrl-C stops all."
wait
