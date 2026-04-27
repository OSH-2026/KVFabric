#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROJECT_ROOT=$(cd "$WORKSPACE_ROOT/../.." && pwd)
UPSTREAM_ROOT="${VLLM_UPSTREAM_ROOT:-$PROJECT_ROOT/vllm-v0.19.0}"
OVERLAY_ROOT="$WORKSPACE_ROOT/overlay"
MANIFEST="$WORKSPACE_ROOT/upstream_manifest.txt"

if [[ ! -d "$UPSTREAM_ROOT/vllm" ]]; then
  echo "Upstream vLLM checkout not found: ${UPSTREAM_ROOT}" >&2
  exit 1
fi

while IFS= read -r rel_path; do
  [[ -z "$rel_path" ]] && continue
  if [[ ! -f "$OVERLAY_ROOT/$rel_path" ]]; then
    echo "Overlay file missing: $OVERLAY_ROOT/$rel_path" >&2
    exit 1
  fi
  cp "$OVERLAY_ROOT/$rel_path" "$UPSTREAM_ROOT/$rel_path"
done <"$MANIFEST"

echo "Applied overlay to: ${UPSTREAM_ROOT}"

