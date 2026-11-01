#!/usr/bin/env bash
# New environment only. Does not alter any existing annotation/training environments.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv="${1:?Usage: bash scripts/benchmark1000_setup.sh /new/environment/path}"
if [[ -e "$venv" ]]; then
  echo "Environment path already exists; choose a new path." >&2
  exit 2
fi
uv venv "$venv"
uv pip install --python "$venv/bin/python" -r "$repo/configs/benchmark1000/requirements.txt"
echo "Run with: BENCHMARK1000_PYTHON=$venv/bin/python bash scripts/benchmark1000.sh --help"
