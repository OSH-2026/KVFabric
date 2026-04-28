#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ $# -lt 3 ]]; then
  echo "Usage: bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/run_quality_variant.sh <variant-file> <suite-config> <run-group-dir>" >&2
  exit 1
fi

variant_file=$(quality_resolve_path "$1")
suite_config=$(quality_resolve_path "$2")
run_group_dir="$3"

if [[ ! -f "$variant_file" ]]; then
  echo "Variant file not found: $variant_file" >&2
  exit 1
fi

if [[ ! -f "$suite_config" ]]; then
  echo "Suite config not found: $suite_config" >&2
  exit 1
fi

load_common_env
ensure_dirs
ensure_quality_dirs
configure_proxy_if_requested
require_venv

# shellcheck disable=SC1090
source "$variant_file"

: "${SUITE_VARIANT_NAME:?SUITE_VARIANT_NAME is required in variant file}"
: "${VARIANT_PRESET:?VARIANT_PRESET is required in variant file}"

load_profile "$VARIANT_PRESET"

max_model_len="${OVERRIDE_MAX_MODEL_LEN:-$MAX_MODEL_LEN}"
gpu_memory_utilization="${OVERRIDE_GPU_MEMORY_UTILIZATION:-$GPU_MEMORY_UTILIZATION}"
max_num_seqs="${OVERRIDE_MAX_NUM_SEQS:-$MAX_NUM_SEQS}"
language_model_only="${OVERRIDE_LANGUAGE_MODEL_ONLY:-${LANGUAGE_MODEL_ONLY:-0}}"
prefix_caching="${OVERRIDE_ENABLE_PREFIX_CACHING:-${ENABLE_PREFIX_CACHING:-auto}}"

output_dir="$run_group_dir/$SUITE_VARIANT_NAME"
mkdir -p "$output_dir"

extra_args=()
if [[ "$language_model_only" == "1" ]]; then
  extra_args+=(--language-model-only)
fi

case "${prefix_caching}" in
  1|true|TRUE|yes|YES)
    extra_args+=(--enable-prefix-caching)
    ;;
  0|false|FALSE|no|NO)
    extra_args+=(--no-enable-prefix-caching)
    ;;
  auto|"")
    ;;
  *)
    echo "Invalid prefix caching override: ${prefix_caching}" >&2
    exit 1
    ;;
esac

VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
HF_HOME="$HF_HOME" \
XDG_CACHE_HOME="$XDG_CACHE_HOME" \
"$(python_bin)" "$QUALITY_ROOT/examples/offline_quality_eval.py" \
  --model "$MODEL_DIR" \
  --suite-config "$suite_config" \
  --output-dir "$output_dir" \
  --variant-name "$SUITE_VARIANT_NAME" \
  --variant-description "${VARIANT_DESCRIPTION:-}" \
  --gpu-memory-utilization "$gpu_memory_utilization" \
  --max-model-len "$max_model_len" \
  --max-num-seqs "$max_num_seqs" \
  "${extra_args[@]}"

echo "Variant output: ${output_dir}"
