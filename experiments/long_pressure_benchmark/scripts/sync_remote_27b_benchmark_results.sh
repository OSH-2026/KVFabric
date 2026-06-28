#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-$REMOTE_HOST}"
REMOTE_SSH_OPTS="${REMOTE_SSH_OPTS:-}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
REMOTE_RUN_PATTERN="${REMOTE_RUN_PATTERN:-*qwen3_5_27b_*_long}"
REMOTE_RUN_ROOT="${REMOTE_RUN_ROOT:-}"
REMOTE_JOB_LOG="${REMOTE_JOB_LOG:-}"
INCLUDE_RAW_JSONL="${INCLUDE_RAW_JSONL:-0}"
INCLUDE_VISUALS="${INCLUDE_VISUALS:-1}"
SUMMARY_OUTPUT_NAME="${SUMMARY_OUTPUT_NAME:-remote_27b_benchmark_summary.md}"

load_common_env
ensure_long_benchmark_dirs

if [[ -z "$REMOTE_RUN_ROOT" ]]; then
  REMOTE_RUN_ROOT=$(ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" \
    "cd '$REMOTE_PROJECT' && find experiments/long_pressure_benchmark/runs -maxdepth 1 -type d -name '$REMOTE_RUN_PATTERN' | sort | tail -n 1")
fi

if [[ -z "$REMOTE_JOB_LOG" ]]; then
  REMOTE_JOB_LOG=$(ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" \
    "cd '$REMOTE_PROJECT' && ls -t vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_*.log 2>/dev/null | head -n 1 || true")
fi

if [[ -z "$REMOTE_RUN_ROOT" ]]; then
  echo "No remote run root matched: ${REMOTE_RUN_PATTERN}" >&2
  exit 1
fi

local_run_root="$PROJECT_ROOT/$REMOTE_RUN_ROOT"
mkdir -p "$local_run_root"

echo "Syncing remote run:"
echo "  remote: ${REMOTE_HOST}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}"
echo "  local:  ${local_run_root}"

if [[ "$INCLUDE_RAW_JSONL" == "1" ]]; then
  if [[ -n "$REMOTE_SSH_OPTS" ]]; then
    rsync -az -e "ssh $REMOTE_SSH_OPTS" \
      "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}/" "$local_run_root/"
  else
    rsync -az "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}/" "$local_run_root/"
  fi
else
  rsync_args=(-az --prune-empty-dirs)
  if [[ -n "$REMOTE_SSH_OPTS" ]]; then
    rsync_args+=(-e "ssh $REMOTE_SSH_OPTS")
  fi
  include_visual_args=()
  if [[ "$INCLUDE_VISUALS" == "1" ]]; then
    include_visual_args+=(
      --include='visuals/*.gif'
      --include='visuals/*.mp4'
      --include='visuals/*.png'
    )
  fi
  rsync "${rsync_args[@]}" \
    --include='*/' \
    --include='run_state.json' \
    --include='trace/trace_summary.json' \
    --include='trace/trace_summary.md' \
    --include='trace/trace.jsonl' \
    --include='policy_state.json' \
    --include='heartbeat.json' \
    --include='online_duration/config.json' \
    --include='online_duration/env.json' \
    --include='online_duration/metrics.json' \
    --include='online_duration/class_metrics.json' \
    --include='online_duration/segment_metrics.json' \
    --include='online_duration/class_segment_metrics.json' \
    --include='online_duration/summary.md' \
    --include='online_duration/rolling_metrics.jsonl' \
    --include='online_duration/rolling_class_metrics.jsonl' \
    --include='online_duration/prometheus_cache_samples.jsonl' \
    --include='online_duration/raw_outputs_sample.jsonl' \
    --include='online_trace/env.json' \
    --include='online_trace/metrics.json' \
    --include='online_trace/class_metrics.json' \
    --include='online_trace/segment_metrics.json' \
    --include='online_trace/class_segment_metrics.json' \
    --include='online_trace/summary.md' \
    --include='online_trace/trace_summary.json' \
    --include='online_trace/rolling_metrics.jsonl' \
    --include='online_trace/rolling_class_metrics.jsonl' \
    --include='online_trace/prometheus_cache_samples.jsonl' \
    --include='online_trace/raw_outputs_sample.jsonl' \
    --include='kvfabric_lifecycle_metrics.json' \
    --include='prometheus_metrics_summary.json' \
    --include='prometheus_metrics_summary.txt' \
    "${include_visual_args[@]}" \
    --exclude='*' \
    "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}/" "$local_run_root/"
fi

mkdir -p "$PROJECT_ROOT/vllm_baseline/runtime_kvfabric_0221/jobs"
if [[ -n "$REMOTE_JOB_LOG" ]]; then
  if [[ -n "$REMOTE_SSH_OPTS" ]]; then
    rsync -az -e "ssh $REMOTE_SSH_OPTS" \
      "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/${REMOTE_JOB_LOG}" \
      "$PROJECT_ROOT/vllm_baseline/runtime_kvfabric_0221/jobs/" || true
  else
    rsync -az "${REMOTE_SSH_TARGET}:${REMOTE_PROJECT}/${REMOTE_JOB_LOG}" \
      "$PROJECT_ROOT/vllm_baseline/runtime_kvfabric_0221/jobs/" || true
  fi
fi

summary_path="$local_run_root/$SUMMARY_OUTPUT_NAME"
"$PROJECT_ROOT/experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py" \
  --run-root "$local_run_root" \
  --output "$summary_path"

echo "Summary written: ${summary_path}"
echo
echo "Raw lifecycle JSONL copied: ${INCLUDE_RAW_JSONL}"
