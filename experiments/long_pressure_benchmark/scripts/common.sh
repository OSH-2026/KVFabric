#!/usr/bin/env bash
set -euo pipefail

LONG_BENCH_COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LONG_BENCH_ROOT=$(cd "$LONG_BENCH_COMMON_DIR/.." && pwd)
EXPERIMENTS_ROOT=$(cd "$LONG_BENCH_ROOT/.." && pwd)
PROJECT_ROOT=$(cd "$EXPERIMENTS_ROOT/.." && pwd)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/vllm_baseline/scripts/common.sh"

ensure_long_benchmark_dirs() {
  mkdir -p "$LONG_BENCH_ROOT/runs"
}

suite_config_path() {
  local filename="$1"
  printf '%s/%s\n' "$LONG_BENCH_ROOT/configs" "$filename"
}

suite_name_from_config() {
  local config_path="$1"
  basename "$config_path" .json
}

suite_run_dir() {
  local preset="$1"
  local suite_name="$2"
  printf '%s/runs/%s_%s_%s\n' \
    "$LONG_BENCH_ROOT" \
    "$(date +'%Y-%m-%d_%H%M%S')" \
    "$preset" \
    "$suite_name"
}
