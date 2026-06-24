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
  hf_download_args=("$MODEL_ID")
  if [[ ${#MODEL_FILES[@]} -gt 0 ]]; then
    hf_download_args+=("${MODEL_FILES[@]}")
  fi

  if [[ -x "${VLLM_VENV_DIR}/bin/hf" ]]; then
    HF_HOME="$HF_HOME" \
    XDG_CACHE_HOME="$XDG_CACHE_HOME" \
    "${VLLM_VENV_DIR}/bin/hf" download \
      "${hf_download_args[@]}" \
      --local-dir "$MODEL_DIR" \
      --max-workers 4
  elif [[ -x "${VLLM_VENV_DIR}/bin/huggingface-cli" ]]; then
    HF_HOME="$HF_HOME" \
    XDG_CACHE_HOME="$XDG_CACHE_HOME" \
    "${VLLM_VENV_DIR}/bin/huggingface-cli" download \
      "${hf_download_args[@]}" \
      --local-dir "$MODEL_DIR" \
      --max-workers 4
  else
    echo "Neither hf nor huggingface-cli was found in ${VLLM_VENV_DIR}/bin." >&2
    exit 1
  fi
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
