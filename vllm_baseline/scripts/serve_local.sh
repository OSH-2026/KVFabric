#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen2_5_0_5b_instruct}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "Model directory not found: ${MODEL_DIR}" >&2
  echo "Run: bash scripts/download_model.sh ${MODEL_PRESET}" >&2
  exit 1
fi

pid_file=$(server_pid_file "$MODEL_PRESET")
log_file=$(server_log_file "$MODEL_PRESET")

if [[ -f "$pid_file" ]]; then
  existing_pid=$(cat "$pid_file")
  if ps -p "$existing_pid" >/dev/null 2>&1; then
    echo "Server already running with PID ${existing_pid}"
    echo "Log file: ${log_file}"
    exit 0
  fi
  rm -f "$pid_file"
fi

echo "Starting vLLM server for ${MODEL_PRESET}"
echo "Log file: ${log_file}"

server_pid=$(
  VLLM_BIN="$(vllm_bin)" \
  MODEL_DIR="$MODEL_DIR" \
  LOG_FILE="$log_file" \
  VLLM_HOST="$VLLM_HOST" \
  VLLM_PORT="$VLLM_PORT" \
  MAX_MODEL_LEN="$MAX_MODEL_LEN" \
  GPU_MEMORY_UTILIZATION="$GPU_MEMORY_UTILIZATION" \
  MAX_NUM_SEQS="$MAX_NUM_SEQS" \
  SERVED_MODEL_NAME="$SERVED_MODEL_NAME" \
  VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
  HF_HOME="$HF_HOME" \
  XDG_CACHE_HOME="$XDG_CACHE_HOME" \
  "$(python_bin)" - <<'PY'
import os
import subprocess
import sys

cmd = [
    os.environ["VLLM_BIN"],
    "serve",
    os.environ["MODEL_DIR"],
    "--host",
    os.environ["VLLM_HOST"],
    "--port",
    os.environ["VLLM_PORT"],
    "--max-model-len",
    os.environ["MAX_MODEL_LEN"],
    "--gpu-memory-utilization",
    os.environ["GPU_MEMORY_UTILIZATION"],
    "--max-num-seqs",
    os.environ["MAX_NUM_SEQS"],
    "--served-model-name",
    os.environ["SERVED_MODEL_NAME"],
]

env = os.environ.copy()
with open(os.environ["LOG_FILE"], "ab", buffering=0) as log_file:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        env=env,
        start_new_session=True,
    )

print(proc.pid)
PY
)
echo "$server_pid" >"$pid_file"

for _ in $(seq 1 180); do
  if curl -fs "http://${VLLM_HOST}:${VLLM_PORT}/health" >/dev/null 2>&1; then
    echo "Server is ready at http://${VLLM_HOST}:${VLLM_PORT}"
    exit 0
  fi
  sleep 1
done

echo "Server did not become ready in time." >&2
tail -n 80 "$log_file" >&2 || true
exit 1
