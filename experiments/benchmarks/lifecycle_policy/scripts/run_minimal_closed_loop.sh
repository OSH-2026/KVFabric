#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BENCH_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CONFIG_PATH="${1:-$BENCH_ROOT/configs/minimal_closed_loop.json}"
RUN_NAME=$(basename "$CONFIG_PATH" .json)
OUTPUT_DIR="${2:-$BENCH_ROOT/runs/$(date +'%Y-%m-%d_%H%M%S')_${RUN_NAME}}"

python3 "$BENCH_ROOT/examples/run_lifecycle_policy.py" \
  --config "$CONFIG_PATH" \
  --output-dir "$OUTPUT_DIR"
