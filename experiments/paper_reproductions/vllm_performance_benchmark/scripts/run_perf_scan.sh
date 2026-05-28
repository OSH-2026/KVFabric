#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

PLAN_FILE="${1:-$PERF_ROOT/plans/qwen3_5_2b_baseline.env}"
PLAN_PATH=$(perf_resolve_path "$PLAN_FILE")

if [[ ! -f "$PLAN_PATH" ]]; then
  echo "Plan file not found: $PLAN_PATH" >&2
  echo "Available plans:" >&2
  find "$PERF_ROOT/plans" -maxdepth 1 -name '*.env' -printf '  %f\n' >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$PLAN_PATH"

if [[ -z "${SUITE_CONFIG:-}" ]]; then
  echo "Plan must define SUITE_CONFIG" >&2
  exit 1
fi
if [[ -z "${VARIANT_FILES:-}" || ${#VARIANT_FILES[@]} -eq 0 ]]; then
  echo "Plan must define VARIANT_FILES as a bash array" >&2
  exit 1
fi

SUITE_CONFIG_PATH=$(perf_resolve_path "$SUITE_CONFIG")
SUITE_NAME=$(perf_suite_name "$SUITE_CONFIG_PATH")
RUN_GROUP_DIR=$(perf_run_group_dir "$SUITE_NAME")

ensure_perf_dirs
mkdir -p "$RUN_GROUP_DIR"

echo "Suite: $SUITE_NAME"
echo "Run group: $RUN_GROUP_DIR"
echo "Variants: ${VARIANT_FILES[*]}"

for variant_file in "${VARIANT_FILES[@]}"; do
  echo ""
  echo "==> Running variant: $variant_file"
  bash "$PERF_ROOT/scripts/run_perf_variant.sh" \
    "$variant_file" \
    "$SUITE_CONFIG_PATH" \
    "$RUN_GROUP_DIR"
done

echo ""
echo "==> Building suite summary..."
bash "$PERF_ROOT/scripts/summarize_suite.sh" "$RUN_GROUP_DIR"

echo ""
echo "Suite complete. Output: $RUN_GROUP_DIR"
