#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

export VLLM_VENV_DIR=.venv_kvfabric_0221
export VLLM_RUNTIME_DIR=vllm_baseline/runtime_kvfabric_0221
export VLLM_REQUIRED_VERSION=0.22.1
export VLLM_SERVER_START_TIMEOUT="${VLLM_SERVER_START_TIMEOUT:-900}"
export VLLM_USE_FLASHINFER_SAMPLER=0
export KV_CACHE_METRICS=1
export KV_CACHE_METRICS_SAMPLE="${KV_CACHE_METRICS_SAMPLE:-1.0}"
export KVFABRIC_PROTECT_MIN_HIT_COUNT="${KVFABRIC_PROTECT_MIN_HIT_COUNT:-1}"
export KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS="${KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS:-800}"
export KVFABRIC_ADMISSION_ANCHOR_BLOCKS="${KVFABRIC_ADMISSION_ANCHOR_BLOCKS:-24}"
export KVFABRIC_RANK_LOG_CANDIDATES="${KVFABRIC_RANK_LOG_CANDIDATES:-1}"
export KVFABRIC_AB_POLICIES="${KVFABRIC_AB_POLICIES:-lru shared_aware family_protect}"

run_root="$VLLM_RUNTIME_DIR/remote_27b_pressure/$(date +'%Y-%m-%d_%H%M%S')_qwen3_5_27b_pressure_validation"
mkdir -p "$run_root"
echo "$run_root" > "$VLLM_RUNTIME_DIR/remote_27b_pressure.latest"

cleanup() {
  local rc=$?
  bash vllm_baseline/scripts/stop_server.sh qwen3_5_27b \
    >"$run_root/final_stop_server.log" 2>&1 || true
  echo "$rc" > "$run_root/status"
  exit "$rc"
}
trap cleanup EXIT

{
  echo "run_root=$run_root"
  echo "started=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "policies=$KVFABRIC_AB_POLICIES"
  echo "rank_log_candidates=$KVFABRIC_RANK_LOG_CANDIDATES"
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

echo "pressure_start=$(date -Is)" >> "$run_root/progress.log"
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_27b \
  experiments/prebenchmark_validation/configs/cache_pressure_hot_revisit_27b_pressure.json \
  > "$run_root/cache_pressure_hot_revisit_27b_pressure.log" 2>&1
grep 'KVFabric A/B output:' "$run_root/cache_pressure_hot_revisit_27b_pressure.log" \
  | tail -1 > "$run_root/cache_pressure_hot_revisit_27b_pressure.run_dir" || true
echo "pressure_done=$(date -Is)" >> "$run_root/progress.log"
echo "completed=$(date -Is)" >> "$run_root/progress.log"
