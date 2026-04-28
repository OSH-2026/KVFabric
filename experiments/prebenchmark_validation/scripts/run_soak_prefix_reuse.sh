#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

bash "$PREBENCH_ROOT/scripts/run_online_batch.sh" \
  "${1:-qwen3_5_2b}" \
  "$(suite_config_path soak_prefix_reuse_20min.json)"
