#!/usr/bin/env bash
set -o pipefail

cd /home/qy-dream/OSH_Project/KVFabric || exit 1

echo "=== soak rerun start $(date --iso-8601=seconds) ==="
pwd

bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b || true
bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_soak_prefix_reuse.sh qwen3_5_2b
status=$?
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b || true

echo "=== soak rerun end $(date --iso-8601=seconds) status=${status} ==="
exit "${status}"
