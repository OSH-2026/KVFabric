#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

for py in \
  .venv/bin/python \
  .venv_kvfabric_0221/bin/python \
  .venv_kvfabric_019/bin/python; do
  if [[ -x "$py" ]]; then
    echo "### $PWD/$py"
    "$py" - <<'PY' 2>&1 || true
import pathlib
import sys
print("python", sys.executable)
try:
    import vllm
    print("vllm", vllm.__version__, pathlib.Path(vllm.__file__).resolve())
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

echo "--- project status ---"
git status --short 2>/dev/null | sed -n '1,120p' || true

echo "--- profile ---"
sed -n '1,120p' vllm_baseline/profiles/qwen3_5_27b.env
