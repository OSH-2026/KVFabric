#!/usr/bin/env bash
set -euo pipefail
cd /home/zhoujiarun/KVFabric
export VLLM_VENV_DIR=.venv_kvfabric_0221
export KVFABRIC_AB_POLICIES=shared_aware
export LONG_BENCH_DURATION_SECONDS=300
export LONG_BENCH_WARMUP_SECONDS=60
export LONG_BENCH_CONCURRENCY=8
export LONG_BENCH_MAX_NUM_SEQS=8
export LONG_BENCH_MAX_NUM_BATCHED_TOKENS=8192
export LONG_BENCH_METRICS_INTERVAL=30
export LONG_BENCH_RAW_SAMPLE_RATE=0.02
export LONG_BENCH_RAW_SAMPLE_LIMIT=500
export KV_CACHE_METRICS_SAMPLE=0.05
bash experiments/prebenchmark_validation/scripts/run_remote_27b_long_benchmark.sh \
  qwen3_5_27b experiments/prebenchmark_validation/configs/qwen3_5_27b_mixed_long_pressure.json
