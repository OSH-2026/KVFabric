#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <run-group-dir>" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

RUN_GROUP_DIR="$1"
if [[ ! -d "$RUN_GROUP_DIR" ]]; then
  echo "Run group directory not found: $RUN_GROUP_DIR" >&2
  exit 1
fi

load_common_env
require_venv

"$(python_bin)" "$PERF_ROOT/examples/summarize_perf_suite.py" "$RUN_GROUP_DIR"
