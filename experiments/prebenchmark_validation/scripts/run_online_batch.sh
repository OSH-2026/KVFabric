#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
ensure_prebenchmark_dirs
require_venv
load_profile "${1:-qwen3_5_2b}"

config_path="${2:-$(suite_config_path online_batch.json)}"
suite_name=$(suite_name_from_config "$config_path")
output_dir=$(suite_run_dir "$MODEL_PRESET" "$suite_name")

if ! curl -fs "http://${VLLM_HOST}:${VLLM_PORT}/health" >/dev/null 2>&1; then
  echo "Server is not healthy at http://${VLLM_HOST}:${VLLM_PORT}/health" >&2
  echo "Run: bash vllm_baseline/scripts/serve_local.sh ${MODEL_PRESET}" >&2
  exit 1
fi

"$(python_bin)" "$PREBENCH_ROOT/examples/online_batch.py" \
  --config "$config_path" \
  --output-dir "$output_dir" \
  --host "$VLLM_HOST" \
  --port "$VLLM_PORT" \
  --model "$SERVED_MODEL_NAME"

echo "Run output: ${output_dir}"
