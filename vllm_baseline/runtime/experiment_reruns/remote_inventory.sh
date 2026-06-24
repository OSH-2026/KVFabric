#!/usr/bin/env bash
set -euo pipefail

echo "HOST=$(hostname)"
echo "HOME=$HOME"
echo "PWD=$PWD"
date

echo "--- gpu ---"
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free \
  --format=csv,noheader

echo "--- project dirs ---"
find /home/zhoujiarun -maxdepth 4 -type d \
  \( -name KVFabric -o -name OSH_Project -o -name ".venv*" -o -name "venv*" \) \
  2>/dev/null | sort | sed -n '1,180p'

echo "--- candidate python envs ---"
for py in \
  /home/zhoujiarun/OSH_Project/KVFabric/.venv/bin/python \
  /home/zhoujiarun/OSH_Project/KVFabric/.venv_kvfabric_0_22_1/bin/python \
  /home/zhoujiarun/KVFabric/.venv/bin/python \
  /home/zhoujiarun/KVFabric/.venv_kvfabric_0_22_1/bin/python \
  /home/zhoujiarun/vllm_0_22_1/bin/python \
  /home/zhoujiarun/.venvs/vllm_0_22_1/bin/python; do
  if [[ -x "$py" ]]; then
    echo "### $py"
    "$py" - <<'PY' 2>&1 || true
import sys
print("python", sys.executable)
try:
    import vllm
    print("vllm", vllm.__version__, vllm.__file__)
except Exception as exc:
    print("vllm_error", type(exc).__name__, exc)
try:
    import torch
    print("torch", torch.__version__, torch.cuda.is_available(),
          torch.cuda.device_count())
except Exception as exc:
    print("torch_error", type(exc).__name__, exc)
PY
  fi
done

echo "--- key project files ---"
find /home/zhoujiarun -maxdepth 5 -type f \
  \( -name qwen3_5_27b.env -o -name apply_to_worktree.sh -o \
     -name run_kvfabric_ab_smoke.sh -o -name serve_local.sh \) \
  2>/dev/null | sort | sed -n '1,220p'
