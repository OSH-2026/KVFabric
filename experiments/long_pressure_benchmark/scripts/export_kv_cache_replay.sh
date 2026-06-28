#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

RUN_ROOT="${RUN_ROOT:-${1:-}}"
POLICY="${POLICY:-${2:-shared_aware}}"
OUTPUT="${OUTPUT:-${3:-}}"

if [[ -z "$RUN_ROOT" ]]; then
  RUN_ROOT=$(find "$LONG_BENCH_ROOT/runs" -maxdepth 1 -type d | sort | tail -n 1)
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="$RUN_ROOT/visuals/replay_${POLICY}.gif"
fi

"$(python_bin)" "$LONG_BENCH_ROOT/dashboard/render_replay_gif.py" \
  --run-root "$RUN_ROOT" \
  --policy "$POLICY" \
  --output "$OUTPUT"
