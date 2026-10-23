#!/usr/bin/env bash
# Create the uv environment for this host. Never replaces an existing one.
# Usage: bash scripts/setup_env.sh [--baseline] [--profile auto|cu130|cu12]
#   --baseline  also install transformers (Depth Anything V2 baseline)
#   --profile   torch build; auto picks from the driver's CUDA version (nvidia-smi):
#               cu130: torch 2.14 + CUDA 13, Python 3.13 (driver >= CUDA 13, e.g. cudahpc51)
#               cu12:  torch 2.9 + CUDA 12, Python 3.11 (older drivers, e.g. cudahpc25)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

baseline=0
profile="${CD_TORCH_PROFILE:-auto}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline) baseline=1; shift ;;
    --profile) profile="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "$profile" == auto ]]; then
  driver_cuda=$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9]*' | awk '{print $3}' || true)
  if [[ -z "$driver_cuda" ]]; then
    echo "Could not read the driver CUDA version from nvidia-smi; pass --profile cu130|cu12" >&2
    exit 1
  fi
  if (( driver_cuda >= 13 )); then profile=cu130; else profile=cu12; fi
  echo "Driver supports CUDA $driver_cuda -> profile $profile"
fi

case "$profile" in
  cu130)
    python_version=3.13
    requirements="$CD_REPO/requirements.txt"
    torch_args=(--torch-backend cu130)
    ;;
  cu12)
    python_version=3.11
    requirements="$CD_REPO/requirements-cu12.txt"
    torch_args=()
    # Reuse the Evaluation project's cache, which already holds these wheels and Python 3.11.
    eval_cache="$CD_STORAGE/.cache/Evaluation"
    [[ -d "$eval_cache/uv" ]] && export UV_CACHE_DIR="$eval_cache/uv"
    [[ -d "$eval_cache/python" ]] && export UV_PYTHON_INSTALL_DIR="$eval_cache/python"
    ;;
  *) echo "unknown profile: $profile" >&2; exit 2 ;;
esac

if [[ -e "$CD_ENV/bin/python" ]]; then
  echo "Environment already exists: $CD_ENV"
  if [[ $baseline == 1 ]]; then
    echo "Adding baseline requirements to the existing environment."
    uv pip install --python "$CD_ENV/bin/python" -r "$CD_REPO/requirements-baseline.txt"
  fi
else
  mkdir -p "$CD_CACHE"
  uv venv --python "$python_version" "$CD_ENV"
  uv pip install --python "$CD_ENV/bin/python" "${torch_args[@]}" -r "$requirements"
  if [[ $baseline == 1 ]]; then
    uv pip install --python "$CD_ENV/bin/python" -r "$CD_REPO/requirements-baseline.txt"
  fi
  echo "$profile" > "$CD_ENV/comics_depth_profile"
fi

"$CD_ENV/bin/python" - <<'EOF'
import torch, torchvision, numpy, PIL
print("torch", torch.__version__, "(CUDA", torch.version.cuda, ") torchvision", torchvision.__version__,
      "numpy", numpy.__version__, "pillow", PIL.__version__)
print("cuda available:", torch.cuda.is_available(), "| devices:", torch.cuda.device_count())
if torch.cuda.is_available():
    x = torch.randn(512, 512, device="cuda")
    print("GPU matmul ok:", torch.isfinite(x @ x).all().item(), "on", torch.cuda.get_device_name(0))
try:
    import transformers
    print("transformers", transformers.__version__)
except ImportError:
    print("transformers not installed (only needed for depth_anything_v2)")
EOF
