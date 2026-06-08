#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$WORKSPACE_ROOT/.." && pwd)
LEGACY_UPSTREAM_ROOT=$(cd "$WORKSPACE_ROOT/../.." && pwd)/vllm-v0.19.0
OVERLAY_ROOT="$WORKSPACE_ROOT/overlay"
MANIFEST="$WORKSPACE_ROOT/upstream_manifest.txt"

resolve_upstream_root() {
  if [[ -n "${VLLM_UPSTREAM_ROOT:-}" ]]; then
    printf '%s\n' "$VLLM_UPSTREAM_ROOT"
    return
  fi

  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    "$REPO_ROOT/.venv/bin/python" - <<'PY' 2>/dev/null && return
import pathlib
import vllm

print(pathlib.Path(vllm.__file__).resolve().parent.parent)
PY
  fi

  printf '%s\n' "$LEGACY_UPSTREAM_ROOT"
}

UPSTREAM_ROOT=$(resolve_upstream_root)

if [[ ! -d "$UPSTREAM_ROOT/vllm" ]]; then
  echo "Upstream vLLM checkout not found: ${UPSTREAM_ROOT}" >&2
  exit 1
fi

while IFS= read -r rel_path; do
  [[ -z "$rel_path" ]] && continue
  mkdir -p "$OVERLAY_ROOT/$(dirname "$rel_path")"
  cp "$UPSTREAM_ROOT/$rel_path" "$OVERLAY_ROOT/$rel_path"
done <"$MANIFEST"

echo "Synced overlay from: ${UPSTREAM_ROOT}"
