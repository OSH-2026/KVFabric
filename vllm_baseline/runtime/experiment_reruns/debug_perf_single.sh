#!/usr/bin/env bash
set -o pipefail

cd /home/qy-dream/OSH_Project/KVFabric || exit 1

source experiments/paper_reproductions/vllm_performance_benchmark/scripts/common.sh
load_common_env
ensure_dirs
require_venv
load_profile qwen3_5_2b

{
  echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
  echo "VLLM_USE_FLASHINFER_SAMPLER=${VLLM_USE_FLASHINFER_SAMPLER:-}"
  timeout 480 vllm bench throughput \
    --model /home/qy-dream/OSH_Project/KVFabric/.cache/models/Qwen3.5-2B \
    --dataset-name random \
    --random-input-len 128 \
    --random-output-len 64 \
    --num-prompts 2 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 2048 \
    --max-num-seqs 16 \
    --no-enable-prefix-caching
  rc=$?
  echo "DEBUG_RC=${rc}"
  exit "${rc}"
} > vllm_baseline/runtime/experiment_reruns/perf_single_debug_with_common.log 2>&1
