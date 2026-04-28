#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
ensure_prebenchmark_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen3_5_2b}"

config_path="${2:-$(suite_config_path offline_batch.json)}"
suite_name=$(suite_name_from_config "$config_path")
output_dir=$(suite_run_dir "$MODEL_PRESET" "$suite_name")

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: ${MODEL_DIR}" >&2
  echo "Run: bash vllm_baseline/scripts/download_model.sh ${MODEL_PRESET}" >&2
  exit 1
fi

extra_args=()
if [[ "${LANGUAGE_MODEL_ONLY:-0}" == "1" ]]; then
  extra_args+=(--language-model-only)
fi
case "${ENABLE_PREFIX_CACHING:-auto}" in
  1|true|TRUE|yes|YES)
    extra_args+=(--enable-prefix-caching)
    ;;
  0|false|FALSE|no|NO)
    extra_args+=(--no-enable-prefix-caching)
    ;;
  auto|"")
    ;;
  *)
    echo "Invalid ENABLE_PREFIX_CACHING=${ENABLE_PREFIX_CACHING}" >&2
    exit 1
    ;;
esac

VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
HF_HOME="$HF_HOME" \
XDG_CACHE_HOME="$XDG_CACHE_HOME" \
"$(python_bin)" "$PREBENCH_ROOT/examples/offline_batch.py" \
  --model "$MODEL_DIR" \
  --config "$config_path" \
  --output-dir "$output_dir" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  "${extra_args[@]}"

echo "Run output: ${output_dir}"
