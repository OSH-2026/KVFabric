#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/KVFabric_Lab4_runtime}"
PROMPTS="${PROMPTS:-$ROOT/prompts/ray_batch_prompts.jsonl}"
ENDPOINTS="${ENDPOINTS:-$ROOT/configs/endpoints.json}"
OUT_DIR="${OUT_DIR:-$ROOT/results/ray_extended}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"
PYTHON="${PYTHON:-python3}"

mkdir -p "$OUT_DIR"

run_case() {
  local label="$1"
  local policy="$2"
  local concurrency="$3"
  shift 3
  echo "=== ray extended case: $label ==="
  "$PYTHON" "$ROOT/scripts/run_ray_batch.py" \
    --prompts "$PROMPTS" \
    --endpoints "$ENDPOINTS" \
    --out-jsonl "$OUT_DIR/${label}.jsonl" \
    --out-summary "$OUT_DIR/${label}_summary.csv" \
    --label "$label" \
    --mode ray \
    --endpoint-policy "$policy" \
    --concurrency "$concurrency" \
    --timeout "$TIMEOUT_SECONDS" \
    --temperature 0.2 \
    "$@"
}

run_case ray_weighted_7_1_c4 weighted_static 4 --endpoint-weights server_gpu=7,local_tunnel=1
run_case ray_weighted_7_1_c8 weighted_static 8 --endpoint-weights server_gpu=7,local_tunnel=1
run_case ray_latency_aware_c4 latency_aware 4
run_case ray_latency_aware_c8 latency_aware 8
