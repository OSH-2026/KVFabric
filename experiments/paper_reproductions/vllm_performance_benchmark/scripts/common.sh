#!/usr/bin/env bash
set -euo pipefail

PERF_COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PERF_ROOT=$(cd "$PERF_COMMON_DIR/.." && pwd)
PAPER_REPRO_ROOT=$(cd "$PERF_ROOT/.." && pwd)
EXPERIMENTS_ROOT=$(cd "$PAPER_REPRO_ROOT/.." && pwd)
PROJECT_ROOT=$(cd "$EXPERIMENTS_ROOT/.." && pwd)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/vllm_baseline/scripts/common.sh"

ensure_perf_dirs() {
  mkdir -p "$PERF_ROOT/runs"
}

perf_resolve_path() {
  local path_value="$1"
  if [[ "$path_value" = /* ]]; then
    printf '%s\n' "$path_value"
  else
    printf '%s/%s\n' "$PERF_ROOT" "$path_value"
  fi
}

perf_suite_name() {
  local config_path="$1"
  basename "$config_path" .json
}

perf_run_group_dir() {
  local suite_name="$1"
  printf '%s/runs/%s_%s\n' \
    "$PERF_ROOT" \
    "$(date +'%Y-%m-%d_%H%M%S')" \
    "$suite_name"
}
