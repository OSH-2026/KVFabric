#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
EXPERIMENT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$EXPERIMENT_ROOT/.." && pwd)
# shellcheck disable=SC1091
source "$REPO_ROOT/vllm_baseline/scripts/common.sh"

load_common_env
ensure_dirs
require_venv
load_profile "${1:-qwen3_5_2b}"

config_path="${2:-$EXPERIMENT_ROOT/configs/online_batch.json}"
run_id=$(date +"%Y-%m-%d_%H%M%S_${MODEL_PRESET}_online_batch")
output_dir="$EXPERIMENT_ROOT/runs/$run_id"

if ! curl -fs "http://${VLLM_HOST}:${VLLM_PORT}/health" >/dev/null 2>&1; then
  echo "Server is not healthy at http://${VLLM_HOST}:${VLLM_PORT}/health" >&2
  echo "Run: bash vllm_baseline/scripts/serve_local.sh ${MODEL_PRESET}" >&2
  exit 1
fi

"$(python_bin)" "$EXPERIMENT_ROOT/examples/online_batch.py" \
  --config "$config_path" \
  --output-dir "$output_dir" \
  --host "$VLLM_HOST" \
  --port "$VLLM_PORT" \
  --model "$SERVED_MODEL_NAME"

echo "Run output: ${output_dir}"
