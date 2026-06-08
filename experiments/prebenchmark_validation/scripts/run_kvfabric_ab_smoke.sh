#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

preset="${1:-qwen2_5_0_5b}"
config_path="${2:-$(suite_config_path prefix_reuse_smoke.json)}"
suite_name=$(suite_name_from_config "$config_path")

load_common_env
ensure_dirs
ensure_prebenchmark_dirs
require_venv
load_profile "$preset"

run_root="$PREBENCH_ROOT/runs/$(date +'%Y-%m-%d_%H%M%S')_${MODEL_PRESET}_${suite_name}_kvfabric_ab"
mkdir -p "$run_root"

run_policy() {
  local policy="$1"
  local policy_dir="$run_root/$policy"
  local lifecycle_log="$policy_dir/kvfabric_lifecycle.jsonl"
  local lifecycle_metrics="$policy_dir/kvfabric_lifecycle_metrics.json"
  local completed=0

  mkdir -p "$policy_dir"
  echo "=== KVFabric policy: ${policy} ==="

  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET"
  trap 'if [[ "$completed" != "1" ]]; then bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true; fi' RETURN

  KVFABRIC_LIFECYCLE=1 \
  KVFABRIC_EVICTION_POLICY="$policy" \
  KVFABRIC_LIFECYCLE_LOG_PATH="$lifecycle_log" \
    bash "$PROJECT_ROOT/vllm_baseline/scripts/serve_local.sh" "$MODEL_PRESET"

	  "$(python_bin)" "$PREBENCH_ROOT/examples/online_batch.py" \
	    --config "$config_path" \
	    --output-dir "$policy_dir/online" \
	    --host "$VLLM_HOST" \
	    --port "$VLLM_PORT" \
	    --model "$SERVED_MODEL_NAME"

	  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
	    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
	    --json > "$policy_dir/prometheus_metrics_summary.json"
	  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
	    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
	    --text > "$policy_dir/prometheus_metrics_summary.txt"

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

read -r -a policies <<<"${KVFABRIC_AB_POLICIES:-lru family_protect}"
for policy in "${policies[@]}"; do
  run_policy "$policy"
done

echo "KVFabric A/B output: ${run_root}"
