#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
require_venv
load_profile "${1:-qwen3_5_2b}"

log_file=$(server_log_file "$MODEL_PRESET")
"$(python_bin)" "$PREBENCH_ROOT/examples/summarize_vllm_log.py" "$log_file"
