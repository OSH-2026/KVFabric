#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen3_5_2b}"

MAX_MODEL_LEN="${VLLM_SERVE_MAX_MODEL_LEN:-$MAX_MODEL_LEN}"
GPU_MEMORY_UTILIZATION="${VLLM_SERVE_GPU_MEMORY_UTILIZATION:-$GPU_MEMORY_UTILIZATION}"
MAX_NUM_SEQS="${VLLM_SERVE_MAX_NUM_SEQS:-$MAX_NUM_SEQS}"
TENSOR_PARALLEL_SIZE="${VLLM_SERVE_TENSOR_PARALLEL_SIZE:-${TENSOR_PARALLEL_SIZE:-1}}"
DTYPE="${VLLM_SERVE_DTYPE:-${DTYPE:-auto}}"
QUANTIZATION="${VLLM_SERVE_QUANTIZATION:-${QUANTIZATION:-}}"
DISTRIBUTED_EXECUTOR_BACKEND="${VLLM_SERVE_DISTRIBUTED_EXECUTOR_BACKEND:-${DISTRIBUTED_EXECUTOR_BACKEND:-}}"
MAX_NUM_BATCHED_TOKENS="${VLLM_SERVE_MAX_NUM_BATCHED_TOKENS:-${MAX_NUM_BATCHED_TOKENS:-}}"
SERVED_MODEL_NAME="${VLLM_SERVE_SERVED_MODEL_NAME:-$SERVED_MODEL_NAME}"
LANGUAGE_MODEL_ONLY="${VLLM_SERVE_LANGUAGE_MODEL_ONLY:-${LANGUAGE_MODEL_ONLY:-0}}"
ENABLE_PREFIX_CACHING="${VLLM_SERVE_ENABLE_PREFIX_CACHING:-${ENABLE_PREFIX_CACHING:-auto}}"

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
  TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}" \
  DTYPE="${DTYPE:-auto}" \
  QUANTIZATION="${QUANTIZATION:-}" \
  DISTRIBUTED_EXECUTOR_BACKEND="${DISTRIBUTED_EXECUTOR_BACKEND:-}" \
  MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-}" \
  SERVED_MODEL_NAME="$SERVED_MODEL_NAME" \
  LANGUAGE_MODEL_ONLY="${LANGUAGE_MODEL_ONLY:-0}" \
  ENABLE_PREFIX_CACHING="${ENABLE_PREFIX_CACHING:-auto}" \
  KV_CACHE_METRICS="${KV_CACHE_METRICS:-0}" \
  KV_CACHE_METRICS_SAMPLE="${KV_CACHE_METRICS_SAMPLE:-0.01}" \
  VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" \
  HF_HOME="$HF_HOME" \
  XDG_CACHE_HOME="$XDG_CACHE_HOME" \
  "$(python_bin)" - <<'PY'
import os
import subprocess
import sys

cmd = [
    sys.executable,
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
    "--tensor-parallel-size",
    os.environ["TENSOR_PARALLEL_SIZE"],
    "--dtype",
    os.environ["DTYPE"],
    "--served-model-name",
    os.environ["SERVED_MODEL_NAME"],
]

if os.environ.get("QUANTIZATION"):
    cmd.extend(["--quantization", os.environ["QUANTIZATION"]])

if os.environ.get("DISTRIBUTED_EXECUTOR_BACKEND"):
    cmd.extend([
        "--distributed-executor-backend",
        os.environ["DISTRIBUTED_EXECUTOR_BACKEND"],
    ])

if os.environ.get("MAX_NUM_BATCHED_TOKENS"):
    cmd.extend([
        "--max-num-batched-tokens",
        os.environ["MAX_NUM_BATCHED_TOKENS"],
    ])

if os.environ.get("LANGUAGE_MODEL_ONLY") == "1":
    cmd.append("--language-model-only")

prefix_caching = os.environ.get("ENABLE_PREFIX_CACHING", "auto").lower()
if prefix_caching in {"1", "true", "yes"}:
    cmd.append("--enable-prefix-caching")
elif prefix_caching in {"0", "false", "no"}:
    cmd.append("--no-enable-prefix-caching")
elif prefix_caching not in {"auto", ""}:
    raise SystemExit(f"Invalid ENABLE_PREFIX_CACHING={prefix_caching}")

if os.environ.get("KV_CACHE_METRICS") == "1":
    cmd.append("--kv-cache-metrics")
    cmd.extend([
        "--kv-cache-metrics-sample",
        os.environ.get("KV_CACHE_METRICS_SAMPLE", "0.01"),
    ])

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

for _ in $(seq 1 "${VLLM_SERVER_START_TIMEOUT:-360}"); do
  if curl -fs "http://${VLLM_HOST}:${VLLM_PORT}/health" >/dev/null 2>&1; then
    echo "Server is ready at http://${VLLM_HOST}:${VLLM_PORT}"
    exit 0
  fi
  sleep 1
done

echo "Server did not become ready in time." >&2
tail -n 80 "$log_file" >&2 || true
exit 1
