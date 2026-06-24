#!/usr/bin/env bash
set -o pipefail

cd /home/qy-dream/OSH_Project/KVFabric || exit 1

echo "=== perf rerun start $(date --iso-8601=seconds) ==="
pwd

bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b || true
bash experiments/paper_reproductions/vllm_performance_benchmark/scripts/run_perf_scan.sh \
  plans/qwen3_5_2b_prefix_ab.env
status=$?

echo "=== perf rerun end $(date --iso-8601=seconds) status=${status} ==="
exit "${status}"
