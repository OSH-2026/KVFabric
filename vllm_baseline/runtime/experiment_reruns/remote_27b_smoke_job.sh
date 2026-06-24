#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

export VLLM_VENV_DIR=.venv_kvfabric_0221
export VLLM_RUNTIME_DIR=vllm_baseline/runtime_kvfabric_0221
export VLLM_REQUIRED_VERSION=0.22.1
export VLLM_SERVER_START_TIMEOUT="${VLLM_SERVER_START_TIMEOUT:-900}"
export VLLM_USE_FLASHINFER_SAMPLER=0

run_root="$VLLM_RUNTIME_DIR/remote_27b_smoke/$(date +'%Y-%m-%d_%H%M%S')_qwen3_5_27b_overlay_smoke"
mkdir -p "$run_root"
echo "$run_root" > "$VLLM_RUNTIME_DIR/remote_27b_smoke.latest"

cleanup() {
  local rc=$?
  bash vllm_baseline/scripts/stop_server.sh qwen3_5_27b \
    >"$run_root/stop_server.log" 2>&1 || true
  cp "$VLLM_RUNTIME_DIR/qwen3_5_27b.log" "$run_root/server.log" 2>/dev/null || true
  echo "$rc" > "$run_root/status"
  exit "$rc"
}
trap cleanup EXIT

{
  echo "run_root=$run_root"
  echo "started=$(date -Is)"
  echo "hostname=$(hostname)"
  "$VLLM_VENV_DIR/bin/python" - <<'PY'
import pathlib
import sys
import torch
import vllm
print("python", sys.executable)
print("vllm", vllm.__version__, pathlib.Path(vllm.__file__).resolve())
print("torch", torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())
PY
  nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free \
    --format=csv,noheader
} > "$run_root/env.log" 2>&1

bash vllm_baseline/scripts/stop_server.sh qwen3_5_27b \
  >"$run_root/pre_stop_server.log" 2>&1 || true

echo "offline_start=$(date -Is)" >> "$run_root/progress.log"
bash vllm_baseline/scripts/run_offline_smoke.sh qwen3_5_27b \
  >"$run_root/offline_smoke.log" 2>&1
echo "offline_done=$(date -Is)" >> "$run_root/progress.log"

echo "serve_start=$(date -Is)" >> "$run_root/progress.log"
bash vllm_baseline/scripts/serve_local.sh qwen3_5_27b \
  >"$run_root/serve_local.log" 2>&1
echo "serve_ready=$(date -Is)" >> "$run_root/progress.log"

bash vllm_baseline/scripts/verify_server.sh qwen3_5_27b \
  >"$run_root/verify_server.log" 2>&1
echo "verify_done=$(date -Is)" >> "$run_root/progress.log"

bash vllm_baseline/scripts/read_metrics.sh --json \
  >"$run_root/prometheus_metrics_summary.json" 2>"$run_root/read_metrics_json.err"
bash vllm_baseline/scripts/read_metrics.sh --text \
  >"$run_root/prometheus_metrics_summary.txt" 2>"$run_root/read_metrics_text.err"
echo "metrics_done=$(date -Is)" >> "$run_root/progress.log"

echo "completed=$(date -Is)" >> "$run_root/progress.log"
