#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-$REMOTE_HOST}"
REMOTE_SSH_OPTS="${REMOTE_SSH_OPTS:-}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

load_common_env

KVFABRIC_4H_SUITE_SKIP_EXISTING="${KVFABRIC_4H_SUITE_SKIP_EXISTING:-0}" \
  bash "$SCRIPT_DIR/run_remote_27b_4h_benchmark_suite.sh"

DASHBOARD_FOLLOW_LATEST=1 \
REMOTE_JOB_LOG="${REMOTE_JOB_LOG:-vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_4h_suite.log}" \
DASHBOARD_PORT="$DASHBOARD_PORT" \
  bash "$SCRIPT_DIR/run_remote_27b_dashboard.sh"
