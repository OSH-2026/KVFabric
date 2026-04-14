#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen2_5_0_5b_instruct}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: ${MODEL_DIR}" >&2
  echo "Run: bash scripts/download_model.sh ${MODEL_PRESET}" >&2
  exit 1
fi

VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
HF_HOME="$HF_HOME" \
XDG_CACHE_HOME="$XDG_CACHE_HOME" \
"$(python_bin)" "$BASELINE_ROOT/examples/offline_smoke.py" \
  --model "$MODEL_DIR" \
  --prompt "$OFFLINE_PROMPT" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS"
