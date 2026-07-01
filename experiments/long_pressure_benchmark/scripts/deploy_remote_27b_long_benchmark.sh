#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-$REMOTE_HOST}"
REMOTE_SSH_OPTS="${REMOTE_SSH_OPTS:-}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
REMOTE_VENV="${REMOTE_VENV:-.venv_kvfabric_0221}"
REMOTE_PRESET="${REMOTE_PRESET:-qwen3_5_27b}"
REMOTE_CONFIG="${REMOTE_CONFIG:-experiments/long_pressure_benchmark/configs/qwen3_5_27b_realistic_10h_pressure.json}"
REMOTE_MODE="${REMOTE_MODE:-sanity}"

load_common_env

sync_paths=(
  "vllm_workspace/overlay/"
  "vllm_workspace/upstream_manifest.txt"
  "vllm_workspace/patches/vllm_overlay.patch"
  "vllm_workspace/scripts/"
  "vllm_baseline/profiles/qwen3_5_9b.env"
  "docs/current/kvfabric_medium_capacity_generalization_design_2026-06-29.md"
  "docs/current/kvfabric_active_experiment_memory.md"
  "docs/current/kvfabric_9b_final_matrix_and_latency_iteration_2026-06-30.md"
  "docs/current/kvfabric_sticky_conversation_fairness_refactor_2026-06-26.md"
  "docs/current/kvfabric_sticky_latency_throughput_refactor_2026-06-27.md"
  "experiments/long_pressure_benchmark/README.md"
  "experiments/long_pressure_benchmark/REMOTE_27B_AUTOMATION.md"
  "experiments/long_pressure_benchmark/examples/online_batch.py"
  "experiments/long_pressure_benchmark/examples/online_duration_loadgen.py"
  "experiments/long_pressure_benchmark/examples/online_trace_loadgen.py"
  "experiments/long_pressure_benchmark/examples/generate_realistic_trace.py"
  "experiments/long_pressure_benchmark/examples/summarize_kvfabric_lifecycle.py"
  "experiments/long_pressure_benchmark/dashboard/"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_mixed_long_pressure.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_realistic_10h_pressure.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_hint_pressure_10h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_saturation_throughput_12h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_saturation_throughput_4h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_enterprise_mixed_trace_12h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_enterprise_mixed_trace_4h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_sticky_conversation_trace_12h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_sticky_conversation_trace_4h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_27b_conversation_sticky_trace_4h.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_capacity_sweep_6m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_daily_dedicated_reuse_40m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_enterprise_normal_25m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_quick_12m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_reuse_45m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_queue_quick_10m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_queue_45m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_foreground_latency_background_quick_8m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_foreground_latency_background_45m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_foreground_latency_background_90m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_lru_gap_throughput_quick_12m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_low_reuse_45m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_low_reuse_low_frequency_20m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_prefill_throughput_medium.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_prefill_reuse_quick_12m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_prefill_reuse_saturation_60m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_enterprise_normal_75m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_quick_daily_8m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_rebuilt_pressure_30m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_rebuilt_quick_12m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_saturation_reuse_proof_30m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_saturation_medium_60m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_sticky_burst_45m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_working_set_hot_gap_quick_8m.json"
  "experiments/long_pressure_benchmark/configs/qwen3_5_9b_working_set_gap_quick_8m.json"
  "experiments/long_pressure_benchmark/scripts/common.sh"
  "experiments/long_pressure_benchmark/scripts/deploy_remote_27b_long_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_long_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_realistic_10h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_hint_pressure_10h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_saturation_throughput_4h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_4h_benchmark_suite.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_trace_long_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_4h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_sticky_conversation_trace_12h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh"
  "experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_quick_loop_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_admission_only_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_eviction_only_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/status_remote_27b_benchmark.sh"
  "experiments/long_pressure_benchmark/scripts/run_remote_27b_dashboard.sh"
  "experiments/long_pressure_benchmark/scripts/start_remote_27b_4h_suite_with_dashboard.sh"
  "experiments/long_pressure_benchmark/scripts/start_remote_27b_sticky_with_dashboard.sh"
  "experiments/long_pressure_benchmark/scripts/export_kv_cache_replay.sh"
  "experiments/long_pressure_benchmark/scripts/sync_remote_27b_benchmark_results.sh"
  "experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py"
  "experiments/long_pressure_benchmark/scripts/recompute_duration_slo_from_lifecycle.py"
  "experiments/long_pressure_benchmark/scripts/analyze_acceptance_run.py"
  "experiments/long_pressure_benchmark/scripts/validate_payload_lengths.py"
)

echo "Syncing KVFabric overlay and long benchmark scripts to ${REMOTE_HOST}:${REMOTE_PROJECT}"
ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "cd '$REMOTE_PROJECT' && \
  mkdir -p \
    docs/current \
    vllm_baseline/profiles \
    experiments/long_pressure_benchmark/configs \
    experiments/long_pressure_benchmark/examples \
    experiments/long_pressure_benchmark/scripts \
    experiments/long_pressure_benchmark/runs && \
  rm -f \
    experiments/prebenchmark_validation/REMOTE_27B_AUTOMATION.md \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_mixed_long_pressure.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_realistic_10h_pressure.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_hint_pressure_10h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_saturation_throughput_12h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_saturation_throughput_4h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_enterprise_mixed_trace_12h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_enterprise_mixed_trace_4h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_sticky_conversation_trace_12h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_sticky_conversation_trace_4h.json \
    experiments/prebenchmark_validation/configs/qwen3_5_27b_conversation_sticky_trace_4h.json \
    experiments/prebenchmark_validation/examples/online_duration_loadgen.py \
    experiments/prebenchmark_validation/examples/online_trace_loadgen.py \
    experiments/prebenchmark_validation/examples/generate_realistic_trace.py \
    experiments/prebenchmark_validation/scripts/deploy_remote_27b_long_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_long_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_realistic_10h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_hint_pressure_10h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_saturation_throughput_4h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_4h_benchmark_suite.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_trace_long_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_enterprise_mixed_trace_4h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_sticky_conversation_trace_12h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh \
    experiments/prebenchmark_validation/scripts/status_remote_27b_benchmark.sh \
    experiments/prebenchmark_validation/scripts/sync_remote_27b_benchmark_results.sh \
    experiments/prebenchmark_validation/scripts/summarize_remote_27b_benchmark_results.py \
    experiments/prebenchmark_validation/scripts/analyze_acceptance_run.py \
    experiments/prebenchmark_validation/scripts/validate_payload_lengths.py"

for path in "${sync_paths[@]}"; do
  if [[ -n "$REMOTE_SSH_OPTS" ]]; then
    rsync -az --delete -e "ssh $REMOTE_SSH_OPTS" \
      "$PROJECT_ROOT/$path" "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/$path"
  else
    rsync -az --delete \
      "$PROJECT_ROOT/$path" "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/$path"
  fi
done

ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "cd '$REMOTE_PROJECT' && \
  VLLM_VENV_DIR='$REMOTE_VENV' bash vllm_workspace/scripts/apply_to_worktree.sh && \
  '$REMOTE_VENV/bin/python' -m py_compile \
    vllm_workspace/overlay/vllm/v1/core/kvfabric_family.py \
    vllm_workspace/overlay/vllm/v1/core/kvfabric_hints.py \
    vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py \
    vllm_workspace/overlay/vllm/v1/core/block_pool.py \
    vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py \
    vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py \
    experiments/long_pressure_benchmark/examples/online_duration_loadgen.py \
    experiments/long_pressure_benchmark/examples/online_trace_loadgen.py \
    experiments/long_pressure_benchmark/examples/generate_realistic_trace.py \
    experiments/long_pressure_benchmark/examples/online_batch.py \
    experiments/long_pressure_benchmark/examples/summarize_kvfabric_lifecycle.py \
    experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py \
    experiments/long_pressure_benchmark/scripts/recompute_duration_slo_from_lifecycle.py \
    experiments/long_pressure_benchmark/scripts/analyze_acceptance_run.py \
    experiments/long_pressure_benchmark/scripts/validate_payload_lengths.py \
    experiments/long_pressure_benchmark/dashboard/kvfabric_run_reader.py \
    experiments/long_pressure_benchmark/dashboard/kv_cache_replay.py \
    experiments/long_pressure_benchmark/dashboard/run_kvfabric_dashboard.py \
    experiments/long_pressure_benchmark/dashboard/run_kvfabric_dashboard_static.py \
    experiments/long_pressure_benchmark/dashboard/render_replay_gif.py && \
  bash -n \
    experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh \
    experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh \
    experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh \
    experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_quick_loop_benchmark.sh \
    experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_admission_only_benchmark.sh \
    experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_benchmark.sh \
    experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_saturation_reuse_proof_eviction_only_benchmark.sh"

if [[ "$REMOTE_MODE" == "sync" ]]; then
  echo "Remote sync and compile completed."
  exit 0
fi

if [[ "$REMOTE_MODE" == "sanity" ]]; then
  ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "cd '$REMOTE_PROJECT' && \
    VLLM_VENV_DIR='$REMOTE_VENV' \
    KVFABRIC_AB_POLICIES='shared_aware' \
    LONG_BENCH_DURATION_SECONDS='300' \
    LONG_BENCH_CONCURRENCY='4' \
    LONG_BENCH_METRICS_INTERVAL='30' \
    bash experiments/long_pressure_benchmark/scripts/run_remote_27b_long_benchmark.sh \
      '$REMOTE_PRESET' '$REMOTE_CONFIG'"
  exit 0
fi

if [[ "$REMOTE_MODE" == "long" ]]; then
  ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "cd '$REMOTE_PROJECT' && \
    VLLM_VENV_DIR='$REMOTE_VENV' \
    KVFABRIC_AB_POLICIES='${KVFABRIC_AB_POLICIES:-lru shared_aware family_protect}' \
    LONG_BENCH_DURATION_SECONDS='${LONG_BENCH_DURATION_SECONDS:-3600}' \
    LONG_BENCH_CONCURRENCY='${LONG_BENCH_CONCURRENCY:-8}' \
    LONG_BENCH_METRICS_INTERVAL='${LONG_BENCH_METRICS_INTERVAL:-30}' \
    bash experiments/long_pressure_benchmark/scripts/run_remote_27b_long_benchmark.sh \
      '$REMOTE_PRESET' '$REMOTE_CONFIG'"
  exit 0
fi

echo "Unknown REMOTE_MODE=${REMOTE_MODE}; expected sync, sanity, or long." >&2
exit 1
