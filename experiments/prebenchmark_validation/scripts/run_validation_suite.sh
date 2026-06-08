#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

preset="${1:-qwen3_5_2b}"
run_medium="${2:-}"

echo "[1/5] offline batch"
bash "$PREBENCH_ROOT/scripts/run_offline_batch.sh" "$preset"

cleanup() {
  bash "$PROJECT_ROOT/vllm_baseline/scripts/stop_server.sh" "$preset" >/dev/null 2>&1 || true
}

trap cleanup EXIT

echo "[2/5] start server"
bash "$PROJECT_ROOT/vllm_baseline/scripts/serve_local.sh" "$preset"

echo "[3/5] online smoke"
bash "$PREBENCH_ROOT/scripts/run_online_batch.sh" "$preset"

echo "[4/5] prefix reuse smoke"
bash "$PREBENCH_ROOT/scripts/run_prefix_reuse_smoke.sh" "$preset"

if [[ "$run_medium" == "--with-medium" ]]; then
  echo "[4.5/5] medium prefix reuse"
  bash "$PREBENCH_ROOT/scripts/run_medium_prefix_reuse.sh" "$preset"
fi

echo "[5/5] summarize vLLM log"
bash "$PREBENCH_ROOT/scripts/summarize_vllm_log.sh" "$preset"
