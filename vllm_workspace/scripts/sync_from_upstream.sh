#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKSPACE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$WORKSPACE_ROOT/.." && pwd)
LEGACY_UPSTREAM_ROOT=$(cd "$WORKSPACE_ROOT/../.." && pwd)/vllm-v0.19.0
OVERLAY_ROOT="$WORKSPACE_ROOT/overlay"
MANIFEST="$WORKSPACE_ROOT/upstream_manifest.txt"
TARGET_VLLM_VERSION="${KVFABRIC_VLLM_VERSION:-0.22.1}"

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

if [[ "${KVFABRIC_SKIP_VLLM_VERSION_CHECK:-0}" != "1" ]]; then
  python3 - "$UPSTREAM_ROOT" "$TARGET_VLLM_VERSION" <<'PY'
import importlib.util
import pathlib
import sys
from importlib.metadata import PathDistribution

root = pathlib.Path(sys.argv[1])
target = sys.argv[2]
dist_infos = sorted(root.glob("vllm-*.dist-info"))
if dist_infos:
    actual = PathDistribution(dist_infos[0]).version
else:
    version_py = root / "vllm" / "version.py"
    if not version_py.exists():
        raise SystemExit(f"Cannot find vLLM version metadata under {root}")
    spec = importlib.util.spec_from_file_location("_kvfabric_vllm_version", version_py)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    actual = getattr(module, "__version__", "")
if actual != target:
    raise SystemExit(
        f"KVFabric overlay expects vLLM {target}, but upstream is {actual}. "
        "Set VLLM_UPSTREAM_ROOT to a clean 0.22.1 tree or set "
        "KVFABRIC_SKIP_VLLM_VERSION_CHECK=1 only for intentional debugging."
    )
PY
fi

while IFS= read -r rel_path; do
  [[ -z "$rel_path" ]] && continue
  if [[ ! -f "$UPSTREAM_ROOT/$rel_path" ]]; then
    echo "Keeping overlay-only file: $rel_path"
    continue
  fi
  mkdir -p "$OVERLAY_ROOT/$(dirname "$rel_path")"
  cp "$UPSTREAM_ROOT/$rel_path" "$OVERLAY_ROOT/$rel_path"
done <"$MANIFEST"

echo "Synced overlay from: ${UPSTREAM_ROOT}"
