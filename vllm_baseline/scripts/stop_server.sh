#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
load_profile "${1:-qwen2_5_0_5b_instruct}"

pid_file=$(server_pid_file "$MODEL_PRESET")

if [[ ! -f "$pid_file" ]]; then
  echo "No PID file found for ${MODEL_PRESET}"
  exit 0
fi

pid=$(cat "$pid_file")
if ps -p "$pid" >/dev/null 2>&1; then
  echo "Stopping server PID ${pid}"
  kill "$pid"
  for _ in $(seq 1 30); do
    if ! ps -p "$pid" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

rm -f "$pid_file"
echo "Stopped ${MODEL_PRESET}"
