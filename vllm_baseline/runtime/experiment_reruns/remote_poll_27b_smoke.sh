#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

pid_file=vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke.pid
latest_file=vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke.latest

echo "--- pid ---"
if [[ -f "$pid_file" ]]; then
  pid=$(cat "$pid_file")
  echo "$pid"
  ps -p "$pid" -o pid=,stat=,etime=,cmd= || true
else
  echo "missing"
fi

echo "--- gpu ---"
nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader

echo "--- latest ---"
if [[ -f "$latest_file" ]]; then
  latest=$(cat "$latest_file")
  echo "$latest"
  echo "--- progress ---"
  sed -n '1,120p' "$latest/progress.log" 2>/dev/null || true
  echo "--- status ---"
  cat "$latest/status" 2>/dev/null || true
  echo
  echo "--- offline tail ---"
  tail -n 35 "$latest/offline_smoke.log" 2>/dev/null || true
  echo "--- serve tail ---"
  tail -n 35 "$latest/serve_local.log" 2>/dev/null || true
  echo "--- verify tail ---"
  tail -n 35 "$latest/verify_server.log" 2>/dev/null || true
else
  echo "missing"
  echo "--- nohup ---"
  tail -n 80 vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke.nohup.log 2>/dev/null || true
fi
