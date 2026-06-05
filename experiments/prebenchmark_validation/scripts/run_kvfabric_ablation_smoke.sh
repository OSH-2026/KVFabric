#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

preset="${1:-qwen2_5_0_5b}"
config_path="${2:-$(suite_config_path cache_pressure_hot_revisit.json)}"
suite_name=$(suite_name_from_config "$config_path")

load_common_env
ensure_dirs
ensure_prebenchmark_dirs
require_venv
load_profile "$preset"

run_root="$PREBENCH_ROOT/runs/$(date +'%Y-%m-%d_%H%M%S')_${MODEL_PRESET}_${suite_name}_kvfabric_ablation"
mkdir -p "$run_root"

run_variant() {
  local variant="$1"
  local policy="$2"
  local ablation="${3:-}"
  local variant_dir="$run_root/$variant"
  local lifecycle_log="$variant_dir/kvfabric_lifecycle.jsonl"
  local lifecycle_metrics="$variant_dir/kvfabric_lifecycle_metrics.json"
  local completed=0

  mkdir -p "$variant_dir"
  echo "=== KVFabric variant: ${variant} policy=${policy} ablation=${ablation:-none} ==="

  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET"
  trap 'if [[ "$completed" != "1" ]]; then bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true; fi' RETURN

  KVFABRIC_LIFECYCLE=1 \
  KVFABRIC_EVICTION_POLICY="$policy" \
  KVFABRIC_RETAIN_ABLATION="$ablation" \
  KVFABRIC_LIFECYCLE_LOG_PATH="$lifecycle_log" \
    bash "$PROJECT_ROOT/vllm_baseline/scripts/serve_local.sh" "$MODEL_PRESET"

  "$(python_bin)" "$PREBENCH_ROOT/examples/online_batch.py" \
    --config "$config_path" \
    --output-dir "$variant_dir/online" \
    --host "$VLLM_HOST" \
    --port "$VLLM_PORT" \
    --model "$SERVED_MODEL_NAME"

  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
    --json > "$variant_dir/prometheus_metrics_summary.json"
  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
    --text > "$variant_dir/prometheus_metrics_summary.txt"

  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET"

  if [[ -f "$lifecycle_log" ]]; then
    "$(python_bin)" "$PREBENCH_ROOT/examples/summarize_kvfabric_lifecycle.py" \
      --input "$lifecycle_log" \
      --output "$lifecycle_metrics"
  else
    echo "Lifecycle log was not created: ${lifecycle_log}" >&2
    return 1
  fi
  completed=1
  trap - RETURN
}

default_variants=(
  "lru:lru:"
  "shared_aware:shared_aware:"
  "shared_no_reuse:shared_aware:reuse"
  "shared_no_prefix:shared_aware:prefix"
  "shared_no_recompute:shared_aware:recompute"
  "family_protect:family_protect:"
  "family_no_reuse:family_protect:reuse"
  "family_no_prefix:family_protect:prefix"
  "family_no_recompute:family_protect:recompute"
)

if [[ -n "${KVFABRIC_ABLATION_VARIANTS:-}" ]]; then
  read -r -a variants <<<"$KVFABRIC_ABLATION_VARIANTS"
else
  variants=("${default_variants[@]}")
fi

for spec in "${variants[@]}"; do
  IFS=: read -r variant policy ablation <<<"$spec"
  if [[ -z "$variant" || -z "$policy" ]]; then
    echo "Invalid variant spec: ${spec}. Expected variant:policy[:ablation]" >&2
    exit 1
  fi
  run_variant "$variant" "$policy" "${ablation:-}"
done

"$(python_bin)" "$PREBENCH_ROOT/examples/compare_kvfabric_ablation.py" \
  "$run_root" \
  --variants "${variants[@]%%:*}" \
  --output "$run_root/ablation_comparison.md"

echo "KVFabric ablation output: ${run_root}"
