#!/usr/bin/env bash
# User-run CPU foundation workflow; no new annotations, GPU inference or release.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench="${BENCH_ROOT:-/data/151-3/comics/ComicsQA_Benchmark}"
version="${1:-v1}"
if [[ ! "$version" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Version must contain only letters, digits, underscore or dash." >&2
  exit 2
fi
reports="$bench/reports/benchmark1000/$version"
store="$bench/items/benchmark1000/$version/candidates"
run() { bash "$repo/scripts/benchmark1000.sh" "$@"; }
run snapshot --out "$reports/legacy_snapshot.json"
run import --source "$bench/items/gen1/v1" --source "$bench/items/gen2/v3" --out "$store"
run verify-store --store "$store"
run check-proofs --store "$store" --bench-root "$bench" --out "$reports/proofs.json"
run preflight --store "$store" --graphs "$bench/evidence/ckg/v1" --out "$reports/preflight.json"
run freeze-policy --policy "$repo/configs/benchmark1000/v1.json" --preflight "$reports/preflight.json" --out "$reports/policy.json"
run select --store "$store" --policy "$reports/policy.json" --pilot --backend cp-sat --seconds 30 --out "$reports/pilot.json"
run verify-legacy --snapshot "$reports/legacy_snapshot.json"
echo "Foundation completed. Review $reports; this is not a final 1000-item build."
