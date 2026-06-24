#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

echo "=== Prefix Cache A/B ==="
echo "Runs throughput scan with prefix cache ON and OFF for comparison."
echo ""

bash "$PERF_ROOT/scripts/run_perf_scan.sh" "$PERF_ROOT/plans/qwen3_5_2b_prefix_ab.env"
