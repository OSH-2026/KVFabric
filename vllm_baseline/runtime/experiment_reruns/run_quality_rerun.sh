#!/usr/bin/env bash
set -o pipefail

cd /home/qy-dream/OSH_Project/KVFabric || exit 1

echo "=== quality rerun start $(date --iso-8601=seconds) ==="
pwd

bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b || true
bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/run_quality_suite.sh \
  plans/qwen3_5_2b_baseline.env
status=$?

echo "=== quality rerun end $(date --iso-8601=seconds) status=${status} ==="
exit "${status}"
