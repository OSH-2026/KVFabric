#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested
load_profile "${1:-}"

echo "Preset: ${MODEL_PRESET}"
echo "Official model: ${MODEL_ID}"
echo "Target directory: ${MODEL_DIR}"

mkdir -p "$MODEL_DIR"

if [[ "${USE_HF_CLI_DOWNLOAD:-0}" == "1" ]]; then
  require_venv
  HF_HOME="$HF_HOME" \
  XDG_CACHE_HOME="$XDG_CACHE_HOME" \
  "$(python_bin)" -m huggingface_hub.commands.huggingface_cli download \
    "$MODEL_ID" \
    "${MODEL_FILES[@]}" \
    --local-dir "$MODEL_DIR" \
    --max-workers 4
  du -sh "$MODEL_DIR"
  exit 0
fi

for file in "${MODEL_FILES[@]}"; do
  target_path="${MODEL_DIR}/${file}"
  partial_path="${target_path}.part"
  mkdir -p "$(dirname "$target_path")"

  if [[ -s "$target_path" ]]; then
    echo "[skip] ${file}"
    continue
  fi

  url="https://huggingface.co/${MODEL_ID}/resolve/main/${file}"
  echo "[download] ${url}"
  curl --fail --location --http1.1 \
    --retry 8 --retry-all-errors --retry-delay 2 \
    --connect-timeout 30 --speed-time 120 --speed-limit 1024 \
    --continue-at - \
    --output "$partial_path" \
    "$url"
  mv "$partial_path" "$target_path"
done

du -sh "$MODEL_DIR"
