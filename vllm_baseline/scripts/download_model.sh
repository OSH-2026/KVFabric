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

for file in "${MODEL_FILES[@]}"; do
  target_path="${MODEL_DIR}/${file}"
  mkdir -p "$(dirname "$target_path")"

  if [[ -s "$target_path" ]]; then
    echo "[skip] ${file}"
    continue
  fi

  url="https://huggingface.co/${MODEL_ID}/resolve/main/${file}"
  echo "[download] ${url}"
  curl --fail --location --http1.1 \
    --retry 8 --retry-all-errors --retry-delay 2 \
    --continue-at - \
    --output "$target_path" \
    "$url"
done

du -sh "$MODEL_DIR"
