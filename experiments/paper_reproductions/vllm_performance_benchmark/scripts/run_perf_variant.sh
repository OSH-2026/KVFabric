#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <variant-file> <suite-config> <run-group-dir>" >&2
  exit 1
fi

VARIANT_FILE="$1"
SUITE_CONFIG="$2"
RUN_GROUP_DIR="$3"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

VARIANT_PATH=$(perf_resolve_path "$VARIANT_FILE")
SUITE_CONFIG_PATH=$(perf_resolve_path "$SUITE_CONFIG")
RUN_GROUP_PATH=$(perf_resolve_path "$RUN_GROUP_DIR")

if [[ ! -f "$VARIANT_PATH" ]]; then
  echo "Variant file not found: $VARIANT_PATH" >&2
  exit 1
fi
if [[ ! -f "$SUITE_CONFIG_PATH" ]]; then
  echo "Suite config not found: $SUITE_CONFIG_PATH" >&2
  exit 1
fi

load_common_env
ensure_dirs
ensure_perf_dirs
configure_proxy_if_requested
require_venv

# shellcheck disable=SC1090
source "$VARIANT_PATH"

if [[ -z "${SUITE_VARIANT_NAME:-}" ]]; then
  echo "Variant must define SUITE_VARIANT_NAME" >&2
  exit 1
fi
if [[ -z "${VARIANT_PRESET:-}" ]]; then
  echo "Variant must define VARIANT_PRESET" >&2
  exit 1
fi

load_profile "$VARIANT_PRESET"

# Re-source variant so its values take precedence over profile defaults
# shellcheck disable=SC1090
source "$VARIANT_PATH"

# Apply overrides (variant values take precedence over profile defaults)
MAX_MODEL_LEN="${OVERRIDE_MAX_MODEL_LEN:-$MAX_MODEL_LEN}"
GPU_MEMORY_UTILIZATION="${OVERRIDE_GPU_MEMORY_UTILIZATION:-$GPU_MEMORY_UTILIZATION}"
MAX_NUM_SEQS="${OVERRIDE_MAX_NUM_SEQS:-$MAX_NUM_SEQS}"
LANGUAGE_MODEL_ONLY="${OVERRIDE_LANGUAGE_MODEL_ONLY:-$LANGUAGE_MODEL_ONLY}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: ${MODEL_DIR}" >&2
  echo "Run: bash vllm_baseline/scripts/download_model.sh ${VARIANT_PRESET}" >&2
  exit 1
fi

VARIANT_OUTPUT_DIR="$RUN_GROUP_PATH/$SUITE_VARIANT_NAME"
mkdir -p "$VARIANT_OUTPUT_DIR"

# Build extra args for prefix caching
extra_args=()
case "${ENABLE_PREFIX_CACHING:-0}" in
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

if [[ "${LANGUAGE_MODEL_ONLY:-0}" == "1" ]]; then
  extra_args+=(--language-model-only)
fi

echo "Model:      $MODEL_DIR"
echo "Variant:    $SUITE_VARIANT_NAME (preset=$VARIANT_PRESET)"
echo "Output:     $VARIANT_OUTPUT_DIR"
echo "GPU util:   $GPU_MEMORY_UTILIZATION"
echo "Max len:    $MAX_MODEL_LEN"
echo "Max seqs:   $MAX_NUM_SEQS"
echo "Prefix cache: ${ENABLE_PREFIX_CACHING:-auto}"
echo ""

PATH="$(dirname "$(python_bin)"):$PATH" \
VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
HF_HOME="$HF_HOME" \
XDG_CACHE_HOME="$XDG_CACHE_HOME" \
"$(python_bin)" "$PERF_ROOT/examples/offline_throughput_scan.py" \
  --model "$MODEL_DIR" \
  --scan-config "$SUITE_CONFIG_PATH" \
  --output-dir "$VARIANT_OUTPUT_DIR" \
  --variant-name "$SUITE_VARIANT_NAME" \
  --variant-description "${VARIANT_DESCRIPTION:-}" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  "${extra_args[@]}"

echo ""
echo "Variant output: $VARIANT_OUTPUT_DIR"
