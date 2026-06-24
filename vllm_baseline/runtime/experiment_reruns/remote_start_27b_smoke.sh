#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric
mkdir -p vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke

nohup bash vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke_job.sh \
  > vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke.nohup.log 2>&1 &
pid=$!

echo "$pid" > vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke.pid
echo "$pid"
