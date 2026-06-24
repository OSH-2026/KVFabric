#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

pid_file=vllm_baseline/runtime_kvfabric_0221/remote_27b_policy.pid
latest_file=vllm_baseline/runtime_kvfabric_0221/remote_27b_policy.latest

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
  sed -n '1,160p' "$latest/progress.log" 2>/dev/null || true
  echo "--- status ---"
  cat "$latest/status" 2>/dev/null || true
  echo
  echo "--- run dirs ---"
  find "$latest" -maxdepth 1 -name '*.run_dir' -type f -print -exec cat {} \; \
    2>/dev/null || true
  echo "--- active server log tail ---"
  tail -n 50 vllm_baseline/runtime_kvfabric_0221/qwen3_5_27b.log \
    2>/dev/null || true
  echo "--- current config log tails ---"
  for log in "$latest"/*.log; do
    [[ -f "$log" ]] || continue
    echo "### $(basename "$log")"
    tail -n 25 "$log" || true
  done
else
  echo "missing"
  echo "--- nohup ---"
  tail -n 80 vllm_baseline/runtime_kvfabric_0221/remote_27b_policy.nohup.log \
    2>/dev/null || true
fi
