#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen3_5_2b}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: ${MODEL_DIR}" >&2
  echo "Run: bash scripts/download_model.sh ${MODEL_PRESET}" >&2
  exit 1
fi

extra_args=()
if [[ "${LANGUAGE_MODEL_ONLY:-0}" == "1" ]]; then
  extra_args+=(--language-model-only)
fi
if [[ -n "${QUANTIZATION:-}" ]]; then
  extra_args+=(--quantization "$QUANTIZATION")
fi
if [[ -n "${DISTRIBUTED_EXECUTOR_BACKEND:-}" ]]; then
  extra_args+=(--distributed-executor-backend "$DISTRIBUTED_EXECUTOR_BACKEND")
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
"$(python_bin)" "$BASELINE_ROOT/examples/offline_smoke.py" \
  --model "$MODEL_DIR" \
  --prompt "$OFFLINE_PROMPT" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
  --dtype "${DTYPE:-auto}" \
  "${extra_args[@]}"
