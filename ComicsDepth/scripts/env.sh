#!/usr/bin/env bash
# Source this file. Big files go under CD_ROOT, caches under CD_CACHE.
export CD_STORAGE="${CD_STORAGE:-/data/151-3/comics}"
export CD_ROOT="${CD_ROOT:-$CD_STORAGE/ComicsDepth}"
export CD_CACHE="${CD_CACHE:-$CD_STORAGE/.cache/ComicsDepth}"
export CD_ENV="${CD_ENV:-$CD_CACHE/venv-$(hostname -s)}"
export CD_REPO="${CD_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Reuse the shared uv cache and managed Python (torch cu130 wheels are already there).
export UV_CACHE_DIR="${UV_CACHE_DIR:-$CD_STORAGE/.cache/uv_cache/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$CD_STORAGE/.cache/uv_cache/python}"

export HF_HOME="${HF_HOME:-$CD_STORAGE/.cache/hf_cache}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TORCH_HOME="${TORCH_HOME:-$CD_CACHE/torch}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$CD_CACHE/xdg}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="$CD_REPO/src${PYTHONPATH:+:$PYTHONPATH}"
