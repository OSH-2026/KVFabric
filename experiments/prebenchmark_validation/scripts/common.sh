#!/usr/bin/env bash
set -euo pipefail

PREBENCH_COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PREBENCH_ROOT=$(cd "$PREBENCH_COMMON_DIR/.." && pwd)
EXPERIMENTS_ROOT=$(cd "$PREBENCH_ROOT/.." && pwd)
PROJECT_ROOT=$(cd "$EXPERIMENTS_ROOT/.." && pwd)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/vllm_baseline/scripts/common.sh"

ensure_prebenchmark_dirs() {
  mkdir -p "$PREBENCH_ROOT/runs"
}

suite_config_path() {
  local filename="$1"
  printf '%s/%s\n' "$PREBENCH_ROOT/configs" "$filename"
}

suite_name_from_config() {
  local config_path="$1"
  basename "$config_path" .json
}

suite_run_dir() {
  local preset="$1"
  local suite_name="$2"
  printf '%s/runs/%s_%s_%s\n' \
    "$PREBENCH_ROOT" \
    "$(date +'%Y-%m-%d_%H%M%S')" \
    "$preset" \
    "$suite_name"
}
