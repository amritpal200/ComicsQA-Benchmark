#!/usr/bin/env bash
# Download pretrained weights. Resumable; never overwrites a completed file.
# Usage: bash scripts/download_weights.sh [--baseline]
#   default     MiDaS v2.1 (midas_v21_384.pt, ~420 MB) -> $CD_STORAGE/models/MiDaS/
#   --baseline  also Depth Anything V2 Large (~1.3 GB) -> HF cache ($HF_HOME)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

baseline=0
for arg in "$@"; do
  case "$arg" in
    --baseline) baseline=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

url="https://github.com/isl-org/MiDaS/releases/download/v2_1/midas_v21_384.pt"
dest="$CD_STORAGE/models/MiDaS"
file="$dest/midas_v21_384.pt"
mkdir -p "$dest"
if [[ -e "$file" ]]; then
  echo "Already present: $file"
else
  curl -L --fail -C - -o "$file.partial" "$url"
  mv "$file.partial" "$file"
fi
if [[ ! -e "$file.sha256" ]]; then
  sha256sum "$file" > "$file.sha256"
fi
cat "$file.sha256"

if [[ $baseline == 1 ]]; then
  [[ -x "$CD_ENV/bin/hf" ]] || { echo "Run: bash scripts/setup_env.sh --baseline" >&2; exit 1; }
  HF_HUB_OFFLINE=0 "$CD_ENV/bin/hf" download depth-anything/Depth-Anything-V2-Large-hf
fi
