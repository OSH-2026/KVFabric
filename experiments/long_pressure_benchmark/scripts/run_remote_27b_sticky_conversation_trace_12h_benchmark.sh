#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

export REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-remote_27b_sticky_conversation_trace_12h}"
export REMOTE_CONFIG="${REMOTE_CONFIG:-experiments/long_pressure_benchmark/configs/qwen3_5_27b_sticky_conversation_trace_12h.json}"

bash "$SCRIPT_DIR/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh"
