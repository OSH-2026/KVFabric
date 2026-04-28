#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

plan_file="${1:-plans/qwen3_5_2b_baseline.env}"
plan_path=$(quality_resolve_path "$plan_file")

if [[ ! -f "$plan_path" ]]; then
  echo "Plan file not found: $plan_path" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$plan_path"

: "${SUITE_CONFIG:?SUITE_CONFIG is required in plan file}"

suite_config=$(quality_resolve_path "$SUITE_CONFIG")
suite_name=$(quality_suite_name "$suite_config")

ensure_quality_dirs
run_group_dir=$(quality_run_group_dir "$suite_name")
mkdir -p "$run_group_dir"

for variant in "${VARIANT_FILES[@]}"; do
  bash "$QUALITY_ROOT/scripts/run_quality_variant.sh" "$variant" "$SUITE_CONFIG" "$run_group_dir"
done

bash "$QUALITY_ROOT/scripts/summarize_suite.sh" "$run_group_dir"
echo "Suite output: ${run_group_dir}"
