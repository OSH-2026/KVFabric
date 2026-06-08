#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$WORKSPACE_ROOT/.." && pwd)
LEGACY_UPSTREAM_ROOT=$(cd "$WORKSPACE_ROOT/../.." && pwd)/vllm-v0.19.0
OVERLAY_ROOT="$WORKSPACE_ROOT/overlay"
PATCH_DIR="$WORKSPACE_ROOT/patches"
PATCH_FILE="$PATCH_DIR/vllm_overlay.patch"
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

mkdir -p "$PATCH_DIR"
: >"$PATCH_FILE"

while IFS= read -r rel_path; do
  [[ -z "$rel_path" ]] && continue
  if [[ ! -f "$OVERLAY_ROOT/$rel_path" ]]; then
    echo "Overlay file missing: $OVERLAY_ROOT/$rel_path" >&2
    exit 1
  fi
  diff -u "$UPSTREAM_ROOT/$rel_path" "$OVERLAY_ROOT/$rel_path" \
    | sed "s#$UPSTREAM_ROOT/##g; s#$OVERLAY_ROOT/##g" >>"$PATCH_FILE" || true
done <"$MANIFEST"

echo "Wrote patch: ${PATCH_FILE}"
