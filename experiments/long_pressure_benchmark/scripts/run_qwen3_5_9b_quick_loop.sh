#!/usr/bin/env bash
set -euo pipefail

BENCH_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "$BENCH_SCRIPT_DIR/common.sh"

PRESET="${PRESET:-qwen3_5_9b}"
TRACE_RUNNER="$BENCH_SCRIPT_DIR/run_remote_27b_trace_long_benchmark.sh"
DURATION_RUNNER="$BENCH_SCRIPT_DIR/run_remote_27b_long_benchmark.sh"

capacity_value() {
  case "$1" in
    small) printf '0.55\n' ;;
    medium) printf '0.70\n' ;;
    large) printf '0.85\n' ;;
    *)
      echo "Unknown KV capacity profile: $1" >&2
      return 1
      ;;
  esac
}

json_value() {
  local config_path="$1"
  local path="$2"
  local default="$3"
  python3 - "$config_path" "$path" "$default" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value = config
for part in sys.argv[2].split("."):
    if isinstance(value, dict) and part in value:
        value = value[part]
    else:
        value = sys.argv[3]
        break
print(value)
PY
}

segment_sum_seconds() {
  local config_path="$1"
  python3 - "$config_path" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
segments = config.get("loadgen", {}).get("segments") or []
print(int(sum(float(segment.get("duration_seconds", 0)) for segment in segments)))
PY
}

apply_common_env() {
  local capacity="$1"
  export VLLM_VENV_DIR="${VLLM_VENV_DIR:-.venv_kvfabric_0221}"
  export VLLM_SERVER_START_TIMEOUT="${VLLM_SERVER_START_TIMEOUT:-900}"
  export KVFABRIC_CAPACITY_PROFILE="$capacity"
  export VLLM_SERVE_GPU_MEMORY_UTILIZATION
  VLLM_SERVE_GPU_MEMORY_UTILIZATION=$(capacity_value "$capacity")
  export KV_CACHE_METRICS="${KV_CACHE_METRICS:-1}"
  export KV_CACHE_METRICS_SAMPLE="${KV_CACHE_METRICS_SAMPLE:-0.05}"
  export KVFABRIC_LOG_BUFFER_SIZE="${KVFABRIC_LOG_BUFFER_SIZE:-8192}"
  export KVFABRIC_HINT_ADMISSION="${KVFABRIC_HINT_ADMISSION:-1}"
  export KVFABRIC_HINT_SCHEDULER="${KVFABRIC_HINT_SCHEDULER:-1}"
  export KVFABRIC_SCHEDULER_AFFINITY="${KVFABRIC_SCHEDULER_AFFINITY:-positive}"
  export KVFABRIC_LRU_ADMISSION_POLICY="${KVFABRIC_LRU_ADMISSION_POLICY:-force}"
  export KVFABRIC_ADMISSION_LIMIT_COLD_MISS="${KVFABRIC_ADMISSION_LIMIT_COLD_MISS:-1}"
  export KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS="${KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS:-400}"
  export KVFABRIC_ADMISSION_ANCHOR_BLOCKS="${KVFABRIC_ADMISSION_ANCHOR_BLOCKS:-1}"
  export KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS="${KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS:-0}"
  export KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS="${KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS:-0}"
  export KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS="${KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS:-0}"
  export KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS="${KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS:-0}"
  export KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS="${KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS:-3072}"
  export KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS="${KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS:-512}"
  export KVFABRIC_ADMISSION_HEAD_WINDOW="${KVFABRIC_ADMISSION_HEAD_WINDOW:-1536}"
  export KVFABRIC_EVICTION_SELECTOR="${KVFABRIC_EVICTION_SELECTOR:-linear}"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN:-64}"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER:-4}"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX="${KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX:-160}"
  export KVFABRIC_EVICTION_RANK_MIN_SCORE="${KVFABRIC_EVICTION_RANK_MIN_SCORE:-0.0}"
  export KVFABRIC_RANK_LOG_EVENTS="${KVFABRIC_RANK_LOG_EVENTS:-1}"
  export KVFABRIC_RANK_LOG_CANDIDATES="${KVFABRIC_RANK_LOG_CANDIDATES:-0}"
}

apply_working_set_throughput_freeze() {
  # Frozen from run 2026-06-29_224542_qwen3_5_9b_working_set_gap_quick_8m.
  export KVFABRIC_ADMISSION_STRENGTH="0.95"
  export KVFABRIC_EVICTION_STRENGTH="0.55"
  export KVFABRIC_SCHEDULER_STRENGTH="0.0"
  export KVFABRIC_SLO_PROTECTION_STRENGTH="0.0"
  export KVFABRIC_LOW_REUSE_CACHE_FRACTION="0.0"
  export KVFABRIC_TRANSIENT_CACHE_FRACTION="0.05"
  export KVFABRIC_BYPASS_CACHE_FRACTION="0.0"
  export KVFABRIC_DURABLE_CACHE_FRACTION="1.0"
  export KVFABRIC_COLD_CACHE_FRACTION="0.0"
  export KVFABRIC_EVICTION_SELECTOR="linear"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN="64"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER="4"
  export KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX="160"
  export KVFABRIC_EVICTION_RANK_MIN_SCORE="0.0"
  export KVFABRIC_EVICTION_SCORE_RECOMPUTE_WEIGHT="0.006"
  export KVFABRIC_EVICTION_SCORE_RECOMPUTE_CAP="12.0"
  export KVFABRIC_EVICTION_SCORE_ANCHOR_BONUS="28.0"
  export KVFABRIC_RANK_LOG_EVENTS="0"
  export KVFABRIC_RANK_LOG_CANDIDATES="0"
  export LONG_BENCH_WARMUP_SECONDS="90"
  export LONG_BENCH_TIMEOUT_SECONDS="600"
  export LONG_BENCH_METRICS_INTERVAL="20"
  export LONG_BENCH_RAW_SAMPLE_RATE="0.02"
  export LONG_BENCH_RAW_SAMPLE_LIMIT="1000"
}

apply_latency_interactive_profile() {
  # Keep this scoped to latency quick loops. The profile targets reusable
  # interactive/session requests in the daily-dedicated trace, while avoiding
  # expensive eviction ranking on the latency hot path.
  export KVFABRIC_ADMISSION_STRENGTH="0.0"
  export KVFABRIC_EVICTION_STRENGTH="0.0"
  export KVFABRIC_SCHEDULER_STRENGTH="1.0"
  export KVFABRIC_SLO_PROTECTION_STRENGTH="0.90"
  export KVFABRIC_LOW_REUSE_CACHE_FRACTION="0.0"
  export KVFABRIC_TRANSIENT_CACHE_FRACTION="0.05"
  export KVFABRIC_BYPASS_CACHE_FRACTION="0.0"
  export KVFABRIC_DURABLE_CACHE_FRACTION="1.0"
  export KVFABRIC_COLD_CACHE_FRACTION="0.0"
  export KVFABRIC_SCHEDULER_AFFINITY="positive"
  export KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW="0"
  export KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW="96"
  export KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO="0.10"
  export KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN="4.0"
  export KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP="0"
  export KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP="16"
  export KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE="1"
  export KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK="8"
  export KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO="0.80"
  export KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP="0"
  export KVFABRIC_SCHEDULER_DEFER_MAX_COUNT="0"
  export KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT="0"
  export KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS="3000"
  export KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS="2500"
  export KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES="short_chat_qa tenant_workflow_hot agent_tool_loop project_code_followup deep_multi_turn_chat long_doc_research_followup"
  export KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS="0"
  export KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS="250"
  export KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS="0"
  export KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO="0.0"
  export KVFABRIC_SCHEDULER_LATENCY_SHORT_OUTPUT_WEIGHT="10.0"
  export KVFABRIC_SCHEDULER_LATENCY_SHORT_OUTPUT_REFERENCE_TOKENS="768"
  export KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS="0"
  export KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS="0"
  export KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_RATIO="0.0"
  export KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_MIN_MS="2500"
  export KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO="0.0"
  export KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_MIN_MS="2500"
  export TRACE_BENCH_MAX_NUM_SEQS="32"
  export TRACE_BENCH_MAX_NUM_BATCHED_TOKENS="24576"
  export KVFABRIC_RANK_LOG_EVENTS="0"
  export KVFABRIC_RANK_LOG_CANDIDATES="0"
}

run_duration_quick() {
  local capacity="$1"
  local policies="$2"
  local config_name="$3"
  local config_path
  config_path=$(suite_config_path "$config_name")
  apply_common_env "$capacity"
  export KVFABRIC_AB_POLICIES="$policies"
  export LONG_BENCH_DURATION_SECONDS
  LONG_BENCH_DURATION_SECONDS=$(segment_sum_seconds "$config_path")
  export LONG_BENCH_WARMUP_SECONDS="${LONG_BENCH_WARMUP_SECONDS:-90}"
  export LONG_BENCH_CONCURRENCY
  LONG_BENCH_CONCURRENCY=$(json_value "$config_path" "concurrency" "72")
  export LONG_BENCH_TIMEOUT_SECONDS="${LONG_BENCH_TIMEOUT_SECONDS:-600}"
  export LONG_BENCH_METRICS_INTERVAL="${LONG_BENCH_METRICS_INTERVAL:-20}"
  export LONG_BENCH_RAW_SAMPLE_RATE="${LONG_BENCH_RAW_SAMPLE_RATE:-0.02}"
  export LONG_BENCH_RAW_SAMPLE_LIMIT="${LONG_BENCH_RAW_SAMPLE_LIMIT:-1000}"
  echo "=== qwen3.5-9b quick duration capacity=${capacity} gpu_mem=${VLLM_SERVE_GPU_MEMORY_UTILIZATION} policies=${KVFABRIC_AB_POLICIES} config=${config_name} ==="
  bash "$DURATION_RUNNER" "$PRESET" "$config_path"
}

run_trace_quick() {
  local capacity="$1"
  local policies="$2"
  local config_name="$3"
  local config_path
  config_path=$(suite_config_path "$config_name")
  apply_common_env "$capacity"
  export KVFABRIC_AB_POLICIES="$policies"
  export TRACE_BENCH_HINT_REGIME
  TRACE_BENCH_HINT_REGIME=$(json_value "$config_path" "trace.hint_regime" "partial_hints")
  export TRACE_BENCH_MAX_MODEL_LEN
  TRACE_BENCH_MAX_MODEL_LEN=$(json_value "$config_path" "trace.max_model_len" "4096")
  export TRACE_BENCH_MAX_IN_FLIGHT
  TRACE_BENCH_MAX_IN_FLIGHT=$(json_value "$config_path" "loadgen.max_in_flight" "56")
  export TRACE_BENCH_WARMUP_SECONDS
  TRACE_BENCH_WARMUP_SECONDS=$(json_value "$config_path" "loadgen.warmup_seconds" "60")
  export TRACE_BENCH_TIMEOUT_SECONDS
  TRACE_BENCH_TIMEOUT_SECONDS=$(json_value "$config_path" "loadgen.timeout_seconds" "900")
  export TRACE_BENCH_SLO_SECONDS
  TRACE_BENCH_SLO_SECONDS=$(json_value "$config_path" "loadgen.slo_seconds" "60")
  export TRACE_BENCH_METRICS_INTERVAL
  TRACE_BENCH_METRICS_INTERVAL=$(json_value "$config_path" "loadgen.metrics_interval" "20")
  export TRACE_BENCH_RAW_SAMPLE_RATE
  TRACE_BENCH_RAW_SAMPLE_RATE=$(json_value "$config_path" "loadgen.raw_sample_rate" "0.05")
  export TRACE_BENCH_RAW_SAMPLE_LIMIT
  TRACE_BENCH_RAW_SAMPLE_LIMIT=$(json_value "$config_path" "loadgen.raw_sample_limit" "900")
  echo "=== qwen3.5-9b quick trace capacity=${capacity} gpu_mem=${VLLM_SERVE_GPU_MEMORY_UTILIZATION} policies=${KVFABRIC_AB_POLICIES} config=${config_name} ==="
  bash "$TRACE_RUNNER" "$PRESET" "$config_path"
}

load_common_env
ensure_dirs
ensure_long_benchmark_dirs

module="${1:-throughput}"
capacity="${2:-medium}"

case "$module" in
  throughput)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_prefill_reuse_quick_12m.json"
    ;;
  throughput_gap)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_throughput}" "qwen3_5_9b_lru_gap_throughput_quick_12m.json"
    ;;
  throughput_working_set)
    (
      apply_working_set_throughput_freeze
      run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_throughput}" "qwen3_5_9b_working_set_gap_quick_8m.json"
    )
    ;;
  prefill_legacy_60m)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_prefill_reuse_saturation_60m.json"
    ;;
  slo_boundary)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_saturation_reuse_proof_30m.json"
    ;;
  rebuilt)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_rebuilt}" "qwen3_5_9b_rebuilt_quick_12m.json"
    ;;
  rebuilt_pressure)
    run_duration_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_rebuilt}" "qwen3_5_9b_rebuilt_pressure_30m.json"
    ;;
  latency)
    (
      apply_latency_interactive_profile
      run_trace_quick "$capacity" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_latency}" "qwen3_5_9b_foreground_latency_background_quick_8m.json"
    )
    ;;
  capacity)
    run_duration_quick "small" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_prefill_reuse_quick_12m.json"
    run_duration_quick "medium" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_prefill_reuse_quick_12m.json"
    run_duration_quick "large" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_prefill_reuse_quick_12m.json"
    ;;
  capacity_sweep_trace)
    run_trace_quick "small" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_capacity_sweep_6m.json"
    run_trace_quick "medium" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_capacity_sweep_6m.json"
    run_trace_quick "large" "${KVFABRIC_QWEN9B_QUICK_POLICIES:-lru kvfabric_admission}" "qwen3_5_9b_capacity_sweep_6m.json"
    ;;
  *)
    echo "Usage: $0 [throughput|throughput_gap|throughput_working_set|prefill_legacy_60m|slo_boundary|rebuilt|rebuilt_pressure|latency|capacity|capacity_sweep_trace] [small|medium|large]" >&2
    exit 2
    ;;
esac
