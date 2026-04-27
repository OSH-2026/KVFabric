#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
EXPERIMENT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

bash "$EXPERIMENT_ROOT/scripts/run_online_batch.sh" \
  "${1:-qwen3_5_2b}" \
  "$EXPERIMENT_ROOT/configs/soak_prefix_reuse_20min.json"

