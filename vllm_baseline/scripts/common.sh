#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASELINE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$BASELINE_ROOT/.." && pwd)

load_common_env() {
  if [[ -f "$BASELINE_ROOT/.env.local" ]]; then
    # shellcheck disable=SC1091
    source "$BASELINE_ROOT/.env.local"
  fi

  : "${VLLM_VENV_DIR:=.venv}"
  : "${VLLM_REQUIRED_VERSION:=0.22.1}"
  : "${VLLM_PIP_PACKAGE:=vllm==${VLLM_REQUIRED_VERSION}}"
  : "${VLLM_MODELS_DIR:=.cache/models}"
  : "${VLLM_CACHE_ROOT:=.cache/vllm}"
  : "${HF_HOME:=.cache/huggingface}"
  : "${XDG_CACHE_HOME:=.cache}"
  : "${VLLM_RUNTIME_DIR:=vllm_baseline/runtime}"
  : "${VLLM_HOST:=127.0.0.1}"
  : "${VLLM_PORT:=8000}"
  : "${VLLM_PROXY_ENABLE:=0}"
  : "${VLLM_PROXY_PORT:=7897}"
  : "${VLLM_PIP_INDEX:=https://download.pytorch.org/whl/cu129}"

  VLLM_VENV_DIR=$(resolve_repo_path "$VLLM_VENV_DIR")
  VLLM_MODELS_DIR=$(resolve_repo_path "$VLLM_MODELS_DIR")
  VLLM_CACHE_ROOT=$(resolve_repo_path "$VLLM_CACHE_ROOT")
  HF_HOME=$(resolve_repo_path "$HF_HOME")
  XDG_CACHE_HOME=$(resolve_repo_path "$XDG_CACHE_HOME")
  VLLM_RUNTIME_DIR=$(resolve_repo_path "$VLLM_RUNTIME_DIR")
}

resolve_repo_path() {
  local path_value="$1"
  if [[ "$path_value" = /* ]]; then
    printf '%s\n' "$path_value"
  else
    printf '%s\n' "$REPO_ROOT/$path_value"
  fi
}

ensure_dirs() {
  mkdir -p "$VLLM_MODELS_DIR" "$VLLM_CACHE_ROOT" "$HF_HOME" "$VLLM_RUNTIME_DIR"
}

configure_proxy_if_requested() {
  if [[ -n "${HTTP_PROXY:-}" || -n "${HTTPS_PROXY:-}" || -n "${ALL_PROXY:-}" ]]; then
    return 0
  fi

  if [[ "${VLLM_PROXY_ENABLE}" != "1" ]]; then
    return 0
  fi

  local gateway
  gateway=$(ip route | awk '/default/ {print $3; exit}')
  if [[ -z "${gateway}" ]]; then
    echo "Unable to detect WSL host gateway for proxy auto-config." >&2
    return 1
  fi

  local proxy_url="http://${gateway}:${VLLM_PROXY_PORT}"
  export HTTP_PROXY="$proxy_url"
  export HTTPS_PROXY="$proxy_url"
  export ALL_PROXY="$proxy_url"
  export http_proxy="$proxy_url"
  export https_proxy="$proxy_url"
  export all_proxy="$proxy_url"
  echo "Using proxy: ${proxy_url}" >&2
}

load_profile() {
  local preset="${1:-}"
  if [[ -z "$preset" ]]; then
    echo "Usage: <script> <preset>" >&2
    echo "Available presets:" >&2
    list_presets >&2
    return 1
  fi

  local profile_file="$BASELINE_ROOT/profiles/${preset}.env"
  if [[ ! -f "$profile_file" ]]; then
    echo "Unknown preset: ${preset}" >&2
    echo "Available presets:" >&2
    list_presets >&2
    return 1
  fi

  # shellcheck disable=SC1090
  source "$profile_file"
  if [[ -n "${HF_ENDPOINT:-}" ]]; then
    export HF_ENDPOINT
  fi
  MODEL_DIR="${VLLM_MODELS_DIR}/${MODEL_DIR_NAME}"
}

list_presets() {
  find "$BASELINE_ROOT/profiles" -maxdepth 1 -type f -name '*.env' -printf '%f\n' | sed 's/\.env$//' | sort
}

require_venv() {
  if [[ ! -x "${VLLM_VENV_DIR}/bin/python" ]]; then
    echo "Virtual environment not found at: ${VLLM_VENV_DIR}" >&2
    echo "Run: bash scripts/setup_venv.sh" >&2
    return 1
  fi
  case ":${PATH}:" in
    *":${VLLM_VENV_DIR}/bin:"*) ;;
    *) export PATH="${VLLM_VENV_DIR}/bin:${PATH}" ;;
  esac
  require_vllm_version
  configure_venv_library_path
}

require_vllm_version() {
  local installed_version
  installed_version=$("${VLLM_VENV_DIR}/bin/python" - <<'PY'
try:
    import vllm
except Exception:
    print("")
else:
    print(vllm.__version__)
PY
)
  if [[ "$installed_version" != "$VLLM_REQUIRED_VERSION" ]]; then
    echo "vLLM version mismatch in ${VLLM_VENV_DIR}: ${installed_version:-not installed}" >&2
    echo "Expected: ${VLLM_REQUIRED_VERSION}" >&2
    echo "Run: VLLM_VENV_DIR=${VLLM_VENV_DIR} bash scripts/setup_venv.sh" >&2
    return 1
  fi
}

configure_venv_library_path() {
  local py_version
  py_version=$("${VLLM_VENV_DIR}/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)

  local lib_dir
  for lib_dir in \
    "${VLLM_VENV_DIR}/lib/python${py_version}/site-packages/nvidia/cu13/lib" \
    "${VLLM_VENV_DIR}/lib/python${py_version}/site-packages/nvidia/cuda_runtime/lib"; do
    if [[ -d "$lib_dir" ]]; then
      case ":${LD_LIBRARY_PATH:-}:" in
        *":${lib_dir}:"*) ;;
        *) export LD_LIBRARY_PATH="${lib_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ;;
      esac
    fi
  done
}

python_bin() {
  printf '%s\n' "${VLLM_VENV_DIR}/bin/python"
}

vllm_bin() {
  printf '%s\n' "${VLLM_VENV_DIR}/bin/vllm"
}

server_pid_file() {
  local preset="$1"
  printf '%s\n' "${VLLM_RUNTIME_DIR}/${preset}.pid"
}

server_log_file() {
  local preset="$1"
  printf '%s\n' "${VLLM_RUNTIME_DIR}/${preset}.log"
}
