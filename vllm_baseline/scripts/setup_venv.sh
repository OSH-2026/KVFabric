#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_common_env
ensure_dirs
configure_proxy_if_requested

if [[ ! -d "$VLLM_VENV_DIR" ]]; then
  echo "Creating virtual environment at ${VLLM_VENV_DIR}"
  python3 -m venv "$VLLM_VENV_DIR"
else
  echo "Reusing virtual environment at ${VLLM_VENV_DIR}"
fi

if ! "$(python_bin)" -c "import vllm, torch" >/dev/null 2>&1; then
  echo "Installing vLLM into ${VLLM_VENV_DIR}"
  "$(python_bin)" -m pip install --upgrade pip setuptools wheel
  "$(python_bin)" -m pip install vllm --extra-index-url "${VLLM_PIP_INDEX}"
else
  echo "vLLM is already installed in ${VLLM_VENV_DIR}"
fi

"$(python_bin)" -c "import vllm, torch; print('vllm', vllm.__version__); print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available())"
