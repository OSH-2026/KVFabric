#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash experiments/paper_reproductions/vllm_performance_benchmark/scripts/summarize_run.sh <run-dir>" >&2
  exit 1
fi

run_dir="$1"
summary_file="$run_dir/summary.md"

if [[ ! -f "$summary_file" ]]; then
  echo "summary.md not found under: $run_dir" >&2
  exit 1
fi

sed -n '1,200p' "$summary_file"
