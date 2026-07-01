#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

export VLLM_VENV_DIR="${VLLM_VENV_DIR:-.venv_kvfabric_0221}"
export KVFABRIC_AB_POLICIES="${KVFABRIC_AB_POLICIES:-lru shared_aware family_protect}"
export TRACE_BENCH_METRICS_INTERVAL="${TRACE_BENCH_METRICS_INTERVAL:-30}"
export TRACE_BENCH_RAW_SAMPLE_RATE="${TRACE_BENCH_RAW_SAMPLE_RATE:-0.02}"
export TRACE_BENCH_RAW_SAMPLE_LIMIT="${TRACE_BENCH_RAW_SAMPLE_LIMIT:-2000}"
export TRACE_BENCH_PROMPT_EXCERPT_CHARS="${TRACE_BENCH_PROMPT_EXCERPT_CHARS:-1200}"
export TRACE_BENCH_MAX_IN_FLIGHT="${TRACE_BENCH_MAX_IN_FLIGHT:-32}"
export TRACE_BENCH_TIMEOUT_SECONDS="${TRACE_BENCH_TIMEOUT_SECONDS:-900}"
export TRACE_BENCH_SLO_SECONDS="${TRACE_BENCH_SLO_SECONDS:-0}"
export TRACE_BENCH_WARMUP_SECONDS="${TRACE_BENCH_WARMUP_SECONDS:-300}"

preset="${1:-qwen3_5_9b}"
config_path="${2:-$(suite_config_path qwen3_5_9b_foreground_latency_background_90m.json)}"
suite_name=$(suite_name_from_config "$config_path")

load_common_env
ensure_dirs
ensure_long_benchmark_dirs
require_venv
load_profile "$preset"

cleanup_trace_loadgens() {
  if [[ "${TRACE_BENCH_KILL_STALE_LOADGENS:-1}" == "1" ]]; then
    pkill -f "$LONG_BENCH_ROOT/examples/online_trace_loadgen.py" 2>/dev/null || true
  fi
}

cleanup_benchmark_processes() {
  stop_policy_heartbeat 2>/dev/null || true
  cleanup_trace_loadgens
  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" >/dev/null 2>&1 || true
}

trap cleanup_benchmark_processes EXIT
cleanup_trace_loadgens

run_root="$LONG_BENCH_ROOT/runs/$(date +'%Y-%m-%d_%H%M%S')_${MODEL_PRESET}_${suite_name}_trace_long"
trace_dir="$run_root/trace"
mkdir -p "$trace_dir"

json_escape() {
  local value="$1"
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$value"
}

write_run_state() {
  local phase="$1"
  local status="$2"
  local current_policy="${3:-}"
  local message="${4:-}"
  cat > "$run_root/run_state.json" <<JSON
{
  "run_root": $(json_escape "$run_root"),
  "model_preset": $(json_escape "$MODEL_PRESET"),
  "suite_name": $(json_escape "$suite_name"),
  "config_path": $(json_escape "$config_path"),
  "phase": $(json_escape "$phase"),
  "status": $(json_escape "$status"),
  "current_policy": $(json_escape "$current_policy"),
  "message": $(json_escape "$message"),
  "updated_at_epoch_seconds": $(date +%s),
  "updated_at": $(json_escape "$(date --iso-8601=seconds)")
}
JSON
}

write_policy_state() {
  local policy_dir="$1"
  local policy="$2"
  local phase="$3"
  local status="$4"
  local exit_code="${5:-0}"
  local message="${6:-}"
  cat > "$policy_dir/policy_state.json" <<JSON
{
  "policy": $(json_escape "$policy"),
  "phase": $(json_escape "$phase"),
  "status": $(json_escape "$status"),
  "exit_code": ${exit_code},
  "message": $(json_escape "$message"),
  "run_root": $(json_escape "$run_root"),
  "policy_dir": $(json_escape "$policy_dir"),
  "updated_at_epoch_seconds": $(date +%s),
  "updated_at": $(json_escape "$(date --iso-8601=seconds)")
}
JSON
}

start_policy_heartbeat() {
  local policy_dir="$1"
  local policy="$2"
  local phase="$3"
  (
    while true; do
      cat > "$policy_dir/heartbeat.json" <<JSON
{
  "policy": $(json_escape "$policy"),
  "phase": $(json_escape "$phase"),
  "pid": $$,
  "updated_at_epoch_seconds": $(date +%s),
  "updated_at": $(json_escape "$(date --iso-8601=seconds)")
}
JSON
      sleep "${TRACE_BENCH_HEARTBEAT_INTERVAL_SECONDS:-15}"
    done
  ) &
  POLICY_HEARTBEAT_PID=$!
}

stop_policy_heartbeat() {
  if [[ -n "${POLICY_HEARTBEAT_PID:-}" ]]; then
    kill "$POLICY_HEARTBEAT_PID" 2>/dev/null || true
    wait "$POLICY_HEARTBEAT_PID" 2>/dev/null || true
    unset POLICY_HEARTBEAT_PID
  fi
}

write_run_state "trace" "running" "" "generating trace"

"$(python_bin)" "$LONG_BENCH_ROOT/examples/generate_realistic_trace.py" \
  --config "$config_path" \
  --output-dir "$trace_dir"

write_run_state "trace" "completed" "" "trace generated"

run_policy() {
  local policy="$1"
  local policy_dir="$run_root/$policy"
  local lifecycle_log="$policy_dir/kvfabric_lifecycle.jsonl"
  local lifecycle_metrics="$policy_dir/kvfabric_lifecycle_metrics.json"
  local completed=0

  mkdir -p "$policy_dir"
  echo "=== Trace KVFabric policy: ${policy} ==="
  echo "Output: ${policy_dir}"
  write_run_state "policy" "running" "$policy" "starting policy"
  write_policy_state "$policy_dir" "$policy" "server_start" "running" 0 "starting vLLM server"

  cleanup_trace_loadgens
  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true
  trap 'if [[ "$completed" != "1" ]]; then bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$MODEL_PRESET" || true; fi' RETURN

  local eviction_policy="$policy"
  local control_profile="${KVFABRIC_PROFILE:-legacy}"
  local control_enable="${KVFABRIC_ENABLE:-1}"
  local admission_strength="${KVFABRIC_ADMISSION_STRENGTH:-}"
  local eviction_strength="${KVFABRIC_EVICTION_STRENGTH:-}"
  local scheduler_strength="${KVFABRIC_SCHEDULER_STRENGTH:-}"
  local slo_protection_strength="${KVFABRIC_SLO_PROTECTION_STRENGTH:-}"
  local hint_trust="${KVFABRIC_HINT_TRUST:-}"
  local low_reuse_cache_fraction="${KVFABRIC_LOW_REUSE_CACHE_FRACTION:-}"
  local transient_cache_fraction="${KVFABRIC_TRANSIENT_CACHE_FRACTION:-}"
  local bypass_cache_fraction="${KVFABRIC_BYPASS_CACHE_FRACTION:-}"
  local durable_cache_fraction="${KVFABRIC_DURABLE_CACHE_FRACTION:-}"
  local cold_cache_fraction="${KVFABRIC_COLD_CACHE_FRACTION:-}"
  if [[ "$policy" == "lru" ]]; then
    admission_policy="${KVFABRIC_LRU_ADMISSION_POLICY:-off}"
    control_profile="off"
    control_enable="0"
    admission_strength="0"
    eviction_strength="0"
    scheduler_strength="0"
    slo_protection_strength="0"
  elif [[ "$policy" == "lru_admission" ]]; then
    eviction_policy="lru"
    admission_policy="${KVFABRIC_LRU_ADMISSION_POLICY:-force}"
    control_profile="${KVFABRIC_POLICY_PROFILE:-admission_dominant}"
    admission_strength="${admission_strength:-0.5}"
    eviction_strength="${eviction_strength:-0.6}"
    scheduler_strength="${scheduler_strength:-0.8}"
    slo_protection_strength="${slo_protection_strength:-0.0}"
  elif [[ "$policy" == "kvfabric_admission" || "$policy" == "kvfabric_admission_dominant" ]]; then
    eviction_policy="lru"
    admission_policy="${KVFABRIC_LRU_ADMISSION_POLICY:-force}"
    control_profile="${KVFABRIC_POLICY_PROFILE:-admission_dominant}"
    admission_strength="${admission_strength:-0.5}"
    eviction_strength="${eviction_strength:-0.6}"
    scheduler_strength="${scheduler_strength:-0.8}"
    slo_protection_strength="${slo_protection_strength:-0.0}"
  elif [[ "$policy" == "kvfabric_throughput" || "$policy" == "kvfabric_throughput_protect" ]]; then
    eviction_policy="shared_aware"
    admission_policy="${KVFABRIC_ADMISSION_POLICY:-auto}"
    control_profile="${KVFABRIC_POLICY_PROFILE:-throughput_protect}"
    admission_strength="${admission_strength:-0.5}"
    eviction_strength="${eviction_strength:-0.6}"
    scheduler_strength="${scheduler_strength:-0.8}"
    slo_protection_strength="${slo_protection_strength:-0.0}"
  elif [[ "$policy" == "kvfabric_rebuilt" || "$policy" == "kvfabric_eviction" ]]; then
    eviction_policy="shared_aware"
    admission_policy="${KVFABRIC_ADMISSION_POLICY:-auto}"
    control_profile="${KVFABRIC_POLICY_PROFILE:-eviction_light}"
    admission_strength="${admission_strength:-0.5}"
    eviction_strength="${eviction_strength:-0.6}"
    scheduler_strength="${scheduler_strength:-0.8}"
    slo_protection_strength="${slo_protection_strength:-0.0}"
  elif [[ "$policy" == "kvfabric_latency" || "$policy" == "kvfabric_latency_protected" ]]; then
    eviction_policy="shared_aware"
    admission_policy="${KVFABRIC_ADMISSION_POLICY:-auto}"
    control_profile="${KVFABRIC_POLICY_PROFILE:-latency_protected}"
    admission_strength="${admission_strength:-0.5}"
    eviction_strength="${eviction_strength:-0.6}"
    scheduler_strength="${scheduler_strength:-0.8}"
    slo_protection_strength="${slo_protection_strength:-0.75}"
  else
    admission_policy="${KVFABRIC_ADMISSION_POLICY:-auto}"
  fi

  if ! KVFABRIC_LIFECYCLE=1 \
  KVFABRIC_ENABLE="$control_enable" \
  KVFABRIC_PROFILE="$control_profile" \
  KVFABRIC_ADMISSION_STRENGTH="$admission_strength" \
  KVFABRIC_EVICTION_STRENGTH="$eviction_strength" \
  KVFABRIC_SCHEDULER_STRENGTH="$scheduler_strength" \
  KVFABRIC_SLO_PROTECTION_STRENGTH="$slo_protection_strength" \
  KVFABRIC_HINT_TRUST="$hint_trust" \
  KVFABRIC_LOW_REUSE_CACHE_FRACTION="$low_reuse_cache_fraction" \
  KVFABRIC_TRANSIENT_CACHE_FRACTION="$transient_cache_fraction" \
  KVFABRIC_BYPASS_CACHE_FRACTION="$bypass_cache_fraction" \
  KVFABRIC_DURABLE_CACHE_FRACTION="$durable_cache_fraction" \
  KVFABRIC_COLD_CACHE_FRACTION="$cold_cache_fraction" \
  KVFABRIC_EVICTION_POLICY="$eviction_policy" \
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
  KVFABRIC_LOG_BUFFER_SIZE="${KVFABRIC_LOG_BUFFER_SIZE:-8192}" \
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
  KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW="${KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW:-0}" \
  KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO="${KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO:-0.55}" \
  KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN="${KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN:-4.0}" \
  KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP="${KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP:-4}" \
  KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE="${KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE:-0}" \
  KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK="${KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK:-4}" \
  KVFABRIC_SCHEDULER_POSITIVE_HIT_WEIGHT="${KVFABRIC_SCHEDULER_POSITIVE_HIT_WEIGHT:-0.004}" \
  KVFABRIC_SCHEDULER_POSITIVE_HIT_MAX_BONUS="${KVFABRIC_SCHEDULER_POSITIVE_HIT_MAX_BONUS:-18.0}" \
  KVFABRIC_SCHEDULER_POSITIVE_SESSION_TURN_BONUS="${KVFABRIC_SCHEDULER_POSITIVE_SESSION_TURN_BONUS:-1.5}" \
  KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO="${KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO:-0.55}" \
  KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP="${KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP:-4}" \
  KVFABRIC_SCHEDULER_DEFER_MAX_COUNT="${KVFABRIC_SCHEDULER_DEFER_MAX_COUNT:-0}" \
  KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT="${KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT:-0}" \
  KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS="${KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS:-0}" \
  KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS="${KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS:-0}" \
  KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS="${KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS:-0}" \
  KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS="${KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS:-0}" \
  KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS="${KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS:-700}" \
  KVFABRIC_PROTECT_MIN_HIT_COUNT="${KVFABRIC_PROTECT_MIN_HIT_COUNT:-1}" \
  KVFABRIC_PROTECT_MIN_SHARE_DEGREE="${KVFABRIC_PROTECT_MIN_SHARE_DEGREE:-2}" \
  KVFABRIC_PROTECT_MIN_BRANCH_FACTOR="${KVFABRIC_PROTECT_MIN_BRANCH_FACTOR:-1}" \
  KVFABRIC_PROTECT_MIN_FAMILY_HITS="${KVFABRIC_PROTECT_MIN_FAMILY_HITS:-2}" \
  KVFABRIC_PROTECT_MIN_FAMILY_BRANCHES="${KVFABRIC_PROTECT_MIN_FAMILY_BRANCHES:-1}" \
  KVFABRIC_PROTECTED_DEPTH="${KVFABRIC_PROTECTED_DEPTH:-2}" \
  KVFABRIC_EVICTION_SELECTOR="${KVFABRIC_EVICTION_SELECTOR:-rank}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN:-512}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER:-16}" \
  KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX:-1024}" \
  KVFABRIC_EVICTION_RANK_MIN_SCORE="${KVFABRIC_EVICTION_RANK_MIN_SCORE:-0.0}" \
  KVFABRIC_EVICTION_SCORE_RECOMPUTE_WEIGHT="${KVFABRIC_EVICTION_SCORE_RECOMPUTE_WEIGHT:-0.01}" \
  KVFABRIC_EVICTION_SCORE_RECOMPUTE_CAP="${KVFABRIC_EVICTION_SCORE_RECOMPUTE_CAP:-16.0}" \
  KVFABRIC_EVICTION_SCORE_ANCHOR_BONUS="${KVFABRIC_EVICTION_SCORE_ANCHOR_BONUS:-24.0}" \
  KVFABRIC_RANK_LOG_EVENTS="${KVFABRIC_RANK_LOG_EVENTS:-0}" \
  KVFABRIC_RANK_LOG_CANDIDATES="${KVFABRIC_RANK_LOG_CANDIDATES:-0}" \
  KV_CACHE_METRICS=1 \
  KV_CACHE_METRICS_SAMPLE="${KV_CACHE_METRICS_SAMPLE:-0.05}" \
  VLLM_SERVE_MAX_MODEL_LEN="${TRACE_BENCH_MAX_MODEL_LEN:-${MAX_MODEL_LEN:-4096}}" \
  VLLM_SERVE_MAX_NUM_SEQS="${TRACE_BENCH_MAX_NUM_SEQS:-${MAX_NUM_SEQS:-10}}" \
  VLLM_SERVE_MAX_NUM_BATCHED_TOKENS="${TRACE_BENCH_MAX_NUM_BATCHED_TOKENS:-${MAX_NUM_BATCHED_TOKENS:-8192}}" \
    bash "$PROJECT_ROOT/vllm_baseline/scripts/serve_local.sh" "$MODEL_PRESET"; then
    write_policy_state "$policy_dir" "$policy" "server_start" "failed" 1 "vLLM server failed to start"
    return 1
  fi

  write_policy_state "$policy_dir" "$policy" "loadgen" "running" 0 "replaying trace"
  start_policy_heartbeat "$policy_dir" "$policy" "loadgen"
  local loadgen_exit=0
  "$(python_bin)" "$LONG_BENCH_ROOT/examples/online_trace_loadgen.py" \
    --trace-dir "$trace_dir" \
    --output-dir "$policy_dir/online_trace" \
    --host "$VLLM_HOST" \
    --port "$VLLM_PORT" \
    --model "$SERVED_MODEL_NAME" \
    --hint-regime "${TRACE_BENCH_HINT_REGIME:-partial_hints}" \
    --warmup-seconds "$TRACE_BENCH_WARMUP_SECONDS" \
    --max-in-flight "$TRACE_BENCH_MAX_IN_FLIGHT" \
    --metrics-interval "$TRACE_BENCH_METRICS_INTERVAL" \
    --raw-sample-rate "$TRACE_BENCH_RAW_SAMPLE_RATE" \
    --raw-sample-limit "$TRACE_BENCH_RAW_SAMPLE_LIMIT" \
    --prompt-excerpt-chars "$TRACE_BENCH_PROMPT_EXCERPT_CHARS" \
    --slo-seconds "$TRACE_BENCH_SLO_SECONDS" \
    --timeout "$TRACE_BENCH_TIMEOUT_SECONDS" || loadgen_exit=$?
  stop_policy_heartbeat
  if [[ "$loadgen_exit" -ne 0 ]]; then
    write_policy_state "$policy_dir" "$policy" "loadgen" "failed" "$loadgen_exit" "trace replay failed"
    return "$loadgen_exit"
  fi

  write_policy_state "$policy_dir" "$policy" "metrics" "running" 0 "reading prometheus and lifecycle metrics"
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
    write_policy_state "$policy_dir" "$policy" "lifecycle" "failed" 1 "lifecycle log was not created"
    echo "Lifecycle log was not created: ${lifecycle_log}" >&2
    return 1
  fi

  completed=1
  write_policy_state "$policy_dir" "$policy" "completed" "completed" 0 "policy completed"
  write_run_state "policy" "completed" "$policy" "policy completed"
  trap - RETURN
}

read -r -a policies <<<"$KVFABRIC_AB_POLICIES"
for policy in "${policies[@]}"; do
  if ! run_policy "$policy"; then
    write_run_state "policy" "failed" "$policy" "policy failed"
    exit 1
  fi
done

write_run_state "summary" "running" "" "building summary"
"$PROJECT_ROOT/experiments/long_pressure_benchmark/scripts/summarize_qwen3_5_9b_benchmark_results.py" \
  --run-root "$run_root" \
  --output "$run_root/qwen3_5_9b_benchmark_summary.md" || true

write_run_state "completed" "completed" "" "run completed"
echo "Remote Qwen3.5-9B trace benchmark output: ${run_root}"
