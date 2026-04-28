#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ $# -ne 1 ]]; then
  echo "Usage: bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/summarize_suite.sh <run-group-dir>" >&2
  exit 1
fi

run_group_dir="$1"
if [[ ! -d "$run_group_dir" ]]; then
  echo "Run group directory not found: $run_group_dir" >&2
  exit 1
fi

load_common_env
require_venv

"$(python_bin)" "$QUALITY_ROOT/examples/summarize_quality_suite.py" "$run_group_dir"
