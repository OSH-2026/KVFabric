#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

export VLLM_VENV_DIR="${VLLM_VENV_DIR:-.venv_kvfabric_0221}"
export KVFABRIC_AB_POLICIES="${KVFABRIC_AB_POLICIES:-lru shared_aware family_protect}"
export LONG_BENCH_DURATION_SECONDS="${LONG_BENCH_DURATION_SECONDS:-3600}"
export LONG_BENCH_CONCURRENCY="${LONG_BENCH_CONCURRENCY:-8}"
export LONG_BENCH_METRICS_INTERVAL="${LONG_BENCH_METRICS_INTERVAL:-30}"
export LONG_BENCH_RAW_SAMPLE_RATE="${LONG_BENCH_RAW_SAMPLE_RATE:-0.01}"
export LONG_BENCH_RAW_SAMPLE_LIMIT="${LONG_BENCH_RAW_SAMPLE_LIMIT:-2000}"

preset="${1:-qwen3_5_27b}"
config_path="${2:-$(suite_config_path qwen3_5_27b_mixed_long_pressure.json)}"
suite_name=$(suite_name_from_config "$config_path")

load_common_env
ensure_dirs
ensure_long_benchmark_dirs
require_venv
load_profile "$preset"

run_root="$LONG_BENCH_ROOT/runs/$(date +'%Y-%m-%d_%H%M%S')_${MODEL_PRESET}_${suite_name}_long"
mkdir -p "$run_root"

run_policy() {
  local policy="$1"
  local policy_dir="$run_root/$policy"
  local lifecycle_log="$policy_dir/kvfabric_lifecycle.jsonl"
  local lifecycle_metrics="$policy_dir/kvfabric_lifecycle_metrics.json"
  local completed=0

  mkdir -p "$policy_dir"
  echo "=== Long KVFabric policy: ${policy} ==="
  echo "Output: ${policy_dir}"

  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true
  trap 'if [[ "$completed" != "1" ]]; then bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true; fi' RETURN

  if [[ "$policy" == "lru" ]]; then
    admission_policy="${KVFABRIC_LRU_ADMISSION_POLICY:-off}"
  else
    admission_policy="${KVFABRIC_ADMISSION_POLICY:-auto}"
  fi

  KVFABRIC_LIFECYCLE=1 \
  KVFABRIC_EVICTION_POLICY="$policy" \
  KVFABRIC_ADMISSION_POLICY="$admission_policy" \
  KVFABRIC_LIFECYCLE_LOG_PATH="$lifecycle_log" \
  KVFABRIC_ENABLE_FAMILY_TREE="${KVFABRIC_ENABLE_FAMILY_TREE:-1}" \
  KVFABRIC_ENABLE_REQUEST_META="${KVFABRIC_ENABLE_REQUEST_META:-1}" \
  KVFABRIC_HINTS="${KVFABRIC_HINTS:-1}" \
  KVFABRIC_HINT_HEADER_TRACE="${KVFABRIC_HINT_HEADER_TRACE:-1}" \
  KVFABRIC_HINT_ADMISSION="${KVFABRIC_HINT_ADMISSION:-1}" \
  KVFABRIC_HINT_SCHEDULER="${KVFABRIC_HINT_SCHEDULER:-1}" \
  KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS="${KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS:-0}" \
  KVFABRIC_HINT_LOW_REUSE_MIN_CACHE_BLOCKS="${KVFABRIC_HINT_LOW_REUSE_MIN_CACHE_BLOCKS:-0}" \
  KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS="${KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS:-0}" \
  KVFABRIC_HINT_BYPASS_MIN_CACHE_BLOCKS="${KVFABRIC_HINT_BYPASS_MIN_CACHE_BLOCKS:-0}" \
  KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS="${KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS:-768}" \
  KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS="${KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS:-1536}" \
  KVFABRIC_HINT_DURABLE_MIN_HIT_TOKENS="${KVFABRIC_HINT_DURABLE_MIN_HIT_TOKENS:-256}" \
  KVFABRIC_HINT_DEFER_LOW_REUSE_RISK_DELTA="${KVFABRIC_HINT_DEFER_LOW_REUSE_RISK_DELTA:-0.10}" \
  KVFABRIC_LOG_BUFFER_SIZE="${KVFABRIC_LOG_BUFFER_SIZE:-1024}" \
  KVFABRIC_ADMISSION_ANCHOR_BLOCKS="${KVFABRIC_ADMISSION_ANCHOR_BLOCKS:-1}" \
  KVFABRIC_ADMISSION_COLD_DISCOVERY_BLOCKS="${KVFABRIC_ADMISSION_COLD_DISCOVERY_BLOCKS:-0}" \
  KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS="${KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS:-768}" \
  KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS="${KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS:-512}" \
  KVFABRIC_ADMISSION_USE_EVICTION_RISK="${KVFABRIC_ADMISSION_USE_EVICTION_RISK:-1}" \
  KVFABRIC_ADMISSION_LIMIT_COLD_MISS="${KVFABRIC_ADMISSION_LIMIT_COLD_MISS:-1}" \
  KVFABRIC_ADMISSION_HEAD_WINDOW="${KVFABRIC_ADMISSION_HEAD_WINDOW:-1024}" \
  KVFABRIC_ADMISSION_RISK_YELLOW_RATIO="${KVFABRIC_ADMISSION_RISK_YELLOW_RATIO:-0.35}" \
  KVFABRIC_ADMISSION_RISK_ORANGE_RATIO="${KVFABRIC_ADMISSION_RISK_ORANGE_RATIO:-0.55}" \
  KVFABRIC_ADMISSION_RISK_RED_RATIO="${KVFABRIC_ADMISSION_RISK_RED_RATIO:-0.75}" \
  KVFABRIC_SCHEDULER_AFFINITY="${KVFABRIC_SCHEDULER_AFFINITY:-risk}" \
  KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO="${KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO:-0.55}" \
  KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP="${KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP:-4}" \
  KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS="${KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS:-700}" \
  KVFABRIC_PROTECT_MIN_HIT_COUNT="${KVFABRIC_PROTECT_MIN_HIT_COUNT:-1}" \
  KVFABRIC_PROTECT_MIN_SHARE_DEGREE="${KVFABRIC_PROTECT_MIN_SHARE_DEGREE:-2}" \
  KVFABRIC_PROTECT_MIN_BRANCH_FACTOR="${KVFABRIC_PROTECT_MIN_BRANCH_FACTOR:-1}" \
  KVFABRIC_PROTECT_MIN_FAMILY_HITS="${KVFABRIC_PROTECT_MIN_FAMILY_HITS:-2}" \
  KVFABRIC_PROTECT_MIN_FAMILY_BRANCHES="${KVFABRIC_PROTECT_MIN_FAMILY_BRANCHES:-1}" \
  KVFABRIC_PROTECTED_DEPTH="${KVFABRIC_PROTECTED_DEPTH:-2}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN:-512}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER:-16}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX:-1024}" \
  KVFABRIC_RANK_LOG_CANDIDATES="${KVFABRIC_RANK_LOG_CANDIDATES:-0}" \
  KV_CACHE_METRICS=1 \
  KV_CACHE_METRICS_SAMPLE="${KV_CACHE_METRICS_SAMPLE:-0.05}" \
  VLLM_SERVE_MAX_MODEL_LEN="${LONG_BENCH_MAX_MODEL_LEN:-${MAX_MODEL_LEN:-2048}}" \
  VLLM_SERVE_MAX_NUM_SEQS="${LONG_BENCH_MAX_NUM_SEQS:-${MAX_NUM_SEQS:-8}}" \
  VLLM_SERVE_MAX_NUM_BATCHED_TOKENS="${LONG_BENCH_MAX_NUM_BATCHED_TOKENS:-${MAX_NUM_BATCHED_TOKENS:-8192}}" \
    bash "$PROJECT_ROOT/vllm_baseline/scripts/serve_local.sh" "$MODEL_PRESET"

  "$(python_bin)" "$LONG_BENCH_ROOT/examples/online_duration_loadgen.py" \
    --config "$config_path" \
    --output-dir "$policy_dir/online_duration" \
    --host "$VLLM_HOST" \
    --port "$VLLM_PORT" \
    --model "$SERVED_MODEL_NAME" \
    --duration-seconds "$LONG_BENCH_DURATION_SECONDS" \
    --warmup-seconds "${LONG_BENCH_WARMUP_SECONDS:-60}" \
    --concurrency "$LONG_BENCH_CONCURRENCY" \
    --metrics-interval "$LONG_BENCH_METRICS_INTERVAL" \
    --raw-sample-rate "$LONG_BENCH_RAW_SAMPLE_RATE" \
    --raw-sample-limit "$LONG_BENCH_RAW_SAMPLE_LIMIT" \
    --timeout "${LONG_BENCH_TIMEOUT_SECONDS:-240}"

  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
    --json > "$policy_dir/prometheus_metrics_summary.json" || true
  bash "$PROJECT_ROOT/vllm_baseline/scripts/read_metrics.sh" \
    --url "http://${VLLM_HOST}:${VLLM_PORT}/metrics" \
    --text > "$policy_dir/prometheus_metrics_summary.txt" || true

  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true

  if [[ -f "$lifecycle_log" ]]; then
    "$(python_bin)" "$LONG_BENCH_ROOT/examples/summarize_kvfabric_lifecycle.py" \
      --input "$lifecycle_log" \
      --output "$lifecycle_metrics"
  else
    echo "Lifecycle log was not created: ${lifecycle_log}" >&2
    return 1
  fi

  completed=1
  trap - RETURN
}

read -r -a policies <<<"$KVFABRIC_AB_POLICIES"
for policy in "${policies[@]}"; do
  run_policy "$policy"
done

echo "Remote 27B long benchmark output: ${run_root}"
