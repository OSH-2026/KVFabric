#!/usr/bin/env bash
set -euo pipefail

QUALITY_COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
QUALITY_ROOT=$(cd "$QUALITY_COMMON_DIR/.." && pwd)
PAPER_REPRO_ROOT=$(cd "$QUALITY_ROOT/.." && pwd)
EXPERIMENTS_ROOT=$(cd "$PAPER_REPRO_ROOT/.." && pwd)
PROJECT_ROOT=$(cd "$EXPERIMENTS_ROOT/.." && pwd)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/vllm_baseline/scripts/common.sh"

ensure_quality_dirs() {
  mkdir -p "$QUALITY_ROOT/runs"
}

quality_resolve_path() {
  local path_value="$1"
  if [[ "$path_value" = /* ]]; then
    printf '%s\n' "$path_value"
  else
    printf '%s/%s\n' "$QUALITY_ROOT" "$path_value"
  fi
}

quality_suite_name() {
  local config_path="$1"
  basename "$config_path" .json
}

quality_run_group_dir() {
  local suite_name="$1"
  printf '%s/runs/%s_%s\n' \
    "$QUALITY_ROOT" \
    "$(date +'%Y-%m-%d_%H%M%S')" \
    "$suite_name"
}
