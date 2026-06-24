#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

overlay_py="$PWD/.venv_kvfabric_0221/bin/python"
overlay_site=$("$overlay_py" - <<'PY'
import pathlib
import vllm
print(pathlib.Path(vllm.__file__).resolve().parent.parent)
PY
)

echo "overlay_python=$overlay_py"
echo "overlay_site=$overlay_site"

VLLM_UPSTREAM_ROOT="$overlay_site" \
  bash vllm_workspace/scripts/apply_to_worktree.sh

"$overlay_py" - <<'PY'
import pathlib
import sys
import torch
import vllm
print("python", sys.executable)
print("vllm", vllm.__version__, pathlib.Path(vllm.__file__).resolve())
print("torch", torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())
import vllm.v1.core.kvfabric_lifecycle as lifecycle
print("kvfabric_lifecycle", pathlib.Path(lifecycle.__file__).resolve())
PY

"$overlay_py" -m py_compile \
  vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py \
  vllm_workspace/overlay/vllm/v1/core/block_pool.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_utils.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_coordinator.py \
  vllm_workspace/overlay/vllm/v1/core/single_type_kv_cache_manager.py \
  vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py \
  vllm_workspace/overlay/vllm/v1/core/sched/output.py \
  vllm_workspace/overlay/vllm/v1/metrics/loggers.py \
  vllm_workspace/overlay/vllm/v1/metrics/stats.py

echo "overlay applied and compiled"
