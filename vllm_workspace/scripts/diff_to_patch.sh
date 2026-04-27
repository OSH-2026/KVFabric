#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROJECT_ROOT=$(cd "$WORKSPACE_ROOT/../.." && pwd)
UPSTREAM_ROOT="${VLLM_UPSTREAM_ROOT:-$PROJECT_ROOT/vllm-v0.19.0}"
OVERLAY_ROOT="$WORKSPACE_ROOT/overlay"
PATCH_DIR="$WORKSPACE_ROOT/patches"
PATCH_FILE="$PATCH_DIR/vllm_overlay.patch"
MANIFEST="$WORKSPACE_ROOT/upstream_manifest.txt"

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

