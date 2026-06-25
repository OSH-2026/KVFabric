#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

export REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-remote_27b_saturation_throughput_4h}"
export REMOTE_CONFIG="${REMOTE_CONFIG:-experiments/long_pressure_benchmark/configs/qwen3_5_27b_saturation_throughput_4h.json}"
export LONG_BENCH_DURATION_SECONDS="${LONG_BENCH_DURATION_SECONDS:-4800}"
export LONG_BENCH_WARMUP_SECONDS="${LONG_BENCH_WARMUP_SECONDS:-200}"

bash "$SCRIPT_DIR/run_remote_27b_saturation_throughput_12h_benchmark.sh"
