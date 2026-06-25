#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

export REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-remote_27b_sticky_conversation_trace_4h}"
export REMOTE_CONFIG="${REMOTE_CONFIG:-experiments/long_pressure_benchmark/configs/qwen3_5_27b_sticky_conversation_trace_4h.json}"
export TRACE_BENCH_WARMUP_SECONDS="${TRACE_BENCH_WARMUP_SECONDS:-100}"

bash "$SCRIPT_DIR/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh"
