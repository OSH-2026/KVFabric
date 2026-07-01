#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-robowalker}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
FINAL_RESULT_NAME="${FINAL_RESULT_NAME:-2026-06-30_qwen3_5_9b_final_matrix}"
REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-qwen9b_12h_tail_enterprise_lowreuse_20260630}"
WAIT_FOR_JOB="${WAIT_FOR_JOB:-0}"
POLL_SECONDS="${POLL_SECONDS:-300}"
SUMMARY_OUTPUT_NAME="${SUMMARY_OUTPUT_NAME:-qwen3_5_9b_benchmark_summary.md}"

load_common_env
ensure_long_benchmark_dirs

FINAL_ROOT="$PROJECT_ROOT/experiments/long_pressure_benchmark/final_12h_results/$FINAL_RESULT_NAME"
mkdir -p \
  "$FINAL_ROOT/job_logs" \
  "$FINAL_ROOT/run_roots" \
  "$FINAL_ROOT/summaries" \
  "$FINAL_ROOT/snapshots/configs" \
  "$FINAL_ROOT/analysis"

remote_job_pid() {
  ssh "$REMOTE_SSH_TARGET" \
    "cat '$REMOTE_PROJECT/vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.pid' 2>/dev/null || true"
}

remote_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  ssh "$REMOTE_SSH_TARGET" "test -d '/proc/$pid'"
}

wait_for_job() {
  local pid
  pid=$(remote_job_pid)
  if [[ -z "$pid" ]]; then
    echo "No remote pid file found for ${REMOTE_JOB_NAME}; archiving without waiting." >&2
    return 0
  fi
  echo "Waiting for remote job ${REMOTE_JOB_NAME} pid=${pid}"
  while remote_pid_alive "$pid"; do
    date '+%Y-%m-%d %H:%M:%S %Z'
    ssh "$REMOTE_SSH_TARGET" \
      "tail -20 '$REMOTE_PROJECT/vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.log' 2>/dev/null || true"
    sleep "$POLL_SECONDS"
  done
  echo "Remote job ${REMOTE_JOB_NAME} finished."
}

latest_remote_run() {
  local pattern="$1"
  ssh "$REMOTE_SSH_TARGET" \
    "cd '$REMOTE_PROJECT' && find experiments/long_pressure_benchmark/runs -maxdepth 1 -type d -name '$pattern' | sort | tail -n 1"
}

sync_job_log() {
  rsync -az \
    "$REMOTE_SSH_TARGET:$REMOTE_PROJECT/vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.log" \
    "$FINAL_ROOT/job_logs/" || true
}

archive_module() {
  local module="$1"
  local pattern="$2"
  local config_name="$3"
  local remote_run
  local local_run
  remote_run=$(latest_remote_run "$pattern")
  if [[ -z "$remote_run" ]]; then
    echo "Missing remote run for module=${module}, pattern=${pattern}" >&2
    return 1
  fi

  local_run="$FINAL_ROOT/run_roots/$module"
  mkdir -p "$local_run"
  echo "Archiving ${module}: ${remote_run}"
  rsync -az "$REMOTE_SSH_TARGET:$REMOTE_PROJECT/$remote_run/" "$local_run/"

  "$PROJECT_ROOT/experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py" \
    --run-root "$local_run" \
    --output "$local_run/$SUMMARY_OUTPUT_NAME"
  cp "$local_run/$SUMMARY_OUTPUT_NAME" "$FINAL_ROOT/summaries/${module}_summary.md"
  cp "$PROJECT_ROOT/experiments/long_pressure_benchmark/configs/$config_name" \
    "$FINAL_ROOT/snapshots/configs/${module}.formal_${config_name}"
}

write_archive_status() {
  local status_path="$FINAL_ROOT/analysis/tail_archive_status.md"
  {
    echo "# 12h Tail Archive Status"
    echo
    echo "- Updated at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "- Remote job: \`${REMOTE_JOB_NAME}\`"
    echo "- Remote project: \`${REMOTE_PROJECT}\`"
    echo "- Final root: \`${FINAL_ROOT}\`"
    echo
    echo "## Modules"
    echo
    for module in enterprise_normal_medium low_reuse; do
      if [[ -f "$FINAL_ROOT/summaries/${module}_summary.md" ]]; then
        echo "- \`${module}\`: archived"
      else
        echo "- \`${module}\`: missing"
      fi
    done
  } > "$status_path"
  echo "Archive status written: $status_path"
}

main() {
  if [[ "$WAIT_FOR_JOB" == "1" ]]; then
    wait_for_job
  fi

  sync_job_log
  archive_module \
    "enterprise_normal_medium" \
    "*qwen3_5_9b_enterprise_normal_75m_trace_long" \
    "qwen3_5_9b_enterprise_normal_75m.json"
  archive_module \
    "low_reuse" \
    "*qwen3_5_9b_low_reuse_45m_trace_long" \
    "qwen3_5_9b_low_reuse_45m.json"
  sync_job_log
  write_archive_status
}

main "$@"
