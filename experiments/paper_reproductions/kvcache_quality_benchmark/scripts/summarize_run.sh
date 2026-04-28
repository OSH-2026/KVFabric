#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/summarize_run.sh <variant-run-dir>" >&2
  exit 1
fi

run_dir="$1"
if [[ ! -f "$run_dir/summary.md" ]]; then
  echo "summary.md not found under: $run_dir" >&2
  exit 1
fi

sed -n '1,160p' "$run_dir/summary.md"
