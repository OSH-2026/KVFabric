#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
require_venv
load_profile "${1:-qwen2_5_0_5b_instruct}"

health_url="http://${VLLM_HOST}:${VLLM_PORT}/health"
models_url="http://${VLLM_HOST}:${VLLM_PORT}/v1/models"

if ! curl -fs "$health_url" >/dev/null 2>&1; then
  echo "Server is not healthy at ${health_url}" >&2
  echo "Run: bash scripts/serve_local.sh ${MODEL_PRESET}" >&2
  exit 1
fi

echo "== /v1/models =="
curl -s "$models_url" | "$(python_bin)" -m json.tool

echo
echo "== OpenAI client smoke test =="
"$(python_bin)" "$BASELINE_ROOT/examples/openai_client_smoke.py" \
  --host "$VLLM_HOST" \
  --port "$VLLM_PORT" \
  --model "$SERVED_MODEL_NAME" \
  --prompt "$VERIFY_PROMPT"
