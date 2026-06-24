#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
REMOTE_RUN_PATTERN="${REMOTE_RUN_PATTERN:-*qwen3_5_27b_realistic_10h_pressure_long}"
REMOTE_RUN_ROOT="${REMOTE_RUN_ROOT:-}"
REMOTE_JOB_LOG="${REMOTE_JOB_LOG:-vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_realistic_10h.log}"
INCLUDE_RAW_JSONL="${INCLUDE_RAW_JSONL:-0}"
SUMMARY_OUTPUT_NAME="${SUMMARY_OUTPUT_NAME:-remote_27b_benchmark_summary.md}"

load_common_env
ensure_prebenchmark_dirs

if [[ -z "$REMOTE_RUN_ROOT" ]]; then
  REMOTE_RUN_ROOT=$(ssh "$REMOTE_HOST" \
    "cd '$REMOTE_PROJECT' && find experiments/prebenchmark_validation/runs -maxdepth 1 -type d -name '$REMOTE_RUN_PATTERN' | sort | tail -n 1")
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
  rsync -az "${REMOTE_HOST}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}/" "$local_run_root/"
else
  rsync -az --prune-empty-dirs \
    --include='*/' \
    --include='online_duration/config.json' \
    --include='online_duration/env.json' \
    --include='online_duration/metrics.json' \
    --include='online_duration/class_metrics.json' \
    --include='online_duration/summary.md' \
    --include='online_duration/rolling_metrics.jsonl' \
    --include='online_duration/prometheus_cache_samples.jsonl' \
    --include='online_duration/raw_outputs_sample.jsonl' \
    --include='kvfabric_lifecycle_metrics.json' \
    --include='prometheus_metrics_summary.json' \
    --include='prometheus_metrics_summary.txt' \
    --exclude='*' \
    "${REMOTE_HOST}:${REMOTE_PROJECT}/${REMOTE_RUN_ROOT}/" "$local_run_root/"
fi

mkdir -p "$PROJECT_ROOT/vllm_baseline/runtime_kvfabric_0221/jobs"
rsync -az "${REMOTE_HOST}:${REMOTE_PROJECT}/${REMOTE_JOB_LOG}" \
  "$PROJECT_ROOT/vllm_baseline/runtime_kvfabric_0221/jobs/" || true

summary_path="$local_run_root/$SUMMARY_OUTPUT_NAME"
"$PROJECT_ROOT/experiments/prebenchmark_validation/scripts/summarize_remote_27b_benchmark_results.py" \
  --run-root "$local_run_root" \
  --output "$summary_path"

echo "Summary written: ${summary_path}"
echo
echo "Raw lifecycle JSONL copied: ${INCLUDE_RAW_JSONL}"
