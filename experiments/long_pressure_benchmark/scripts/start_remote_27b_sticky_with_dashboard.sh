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

suite_started_epoch=$(ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "date +%s")
bash "$SCRIPT_DIR/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh"

remote_run_root=""
for _ in $(seq 1 "${DASHBOARD_RUN_WAIT_ATTEMPTS:-60}"); do
  sleep "${DASHBOARD_START_DELAY_SECONDS:-5}"
  remote_run_root=$(ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" \
    "cd '$REMOTE_PROJECT' && find experiments/long_pressure_benchmark/runs -maxdepth 1 -type d -name '*sticky_conversation_trace_4h*' -printf '%T@ %p\n' | awk -v start='$suite_started_epoch' '\$1 >= start - 5 {print}' | sort -nr | head -n 1 | cut -d' ' -f2-")
  if [[ -n "$remote_run_root" ]]; then
    break
  fi
done
if [[ -z "$remote_run_root" ]]; then
  echo "Timed out waiting for remote sticky run directory." >&2
  exit 1
fi

REMOTE_RUN_ROOT="$remote_run_root" \
DASHBOARD_PORT="$DASHBOARD_PORT" \
bash "$SCRIPT_DIR/run_remote_27b_dashboard.sh"
