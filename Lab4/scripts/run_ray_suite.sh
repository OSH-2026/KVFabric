#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/KVFabric_Lab4_runtime}"
PROMPTS="${PROMPTS:-$ROOT/prompts/ray_batch_prompts.jsonl}"
ENDPOINTS="${ENDPOINTS:-$ROOT/configs/endpoints.json}"
OUT_DIR="${OUT_DIR:-$ROOT/results/ray}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"
PYTHON="${PYTHON:-python3}"

mkdir -p "$OUT_DIR"

run_case() {
  local label="$1"
  local mode="$2"
  local concurrency="$3"
  echo "=== ray case: $label ==="
  "$PYTHON" "$ROOT/scripts/run_ray_batch.py" \
    --prompts "$PROMPTS" \
    --endpoints "$ENDPOINTS" \
    --out-jsonl "$OUT_DIR/${label}.jsonl" \
    --out-summary "$OUT_DIR/${label}_summary.csv" \
    --label "$label" \
    --mode "$mode" \
    --endpoint-policy round_robin \
    --concurrency "$concurrency" \
    --timeout "$TIMEOUT_SECONDS" \
    --temperature 0.2
}

run_case ray_round_robin_c2 ray 2
run_case ray_round_robin_c4 ray 4
run_case ray_round_robin_c8 ray 8
