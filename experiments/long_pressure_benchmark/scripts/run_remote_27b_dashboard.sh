#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-$REMOTE_HOST}"
REMOTE_SSH_OPTS="${REMOTE_SSH_OPTS:-}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
REMOTE_VENV="${REMOTE_VENV:-.venv_kvfabric_0221}"
REMOTE_RUN_ROOT="${REMOTE_RUN_ROOT:-}"
REMOTE_JOB_LOG="${REMOTE_JOB_LOG:-vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_sticky_conversation_trace_4h.log}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
INSTALL_DASHBOARD_DEPS="${INSTALL_DASHBOARD_DEPS:-1}"

load_common_env

ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_PROJECT"
if [[ -z "$REMOTE_RUN_ROOT" ]]; then
  REMOTE_RUN_ROOT=\$(find experiments/long_pressure_benchmark/runs -maxdepth 1 -type d | sort | tail -n 1)
fi
python_bin="$REMOTE_VENV/bin/python"
if ! "\$python_bin" - <<'PY'
import importlib
for name in ("streamlit", "plotly", "pandas", "matplotlib", "imageio"):
    importlib.import_module(name)
PY
then
  if [[ "$INSTALL_DASHBOARD_DEPS" == "1" ]]; then
    "\$python_bin" -m pip install -r experiments/long_pressure_benchmark/dashboard/requirements.txt
  else
    echo "Dashboard dependencies are missing. Run with INSTALL_DASHBOARD_DEPS=1 or install dashboard/requirements.txt." >&2
    exit 1
  fi
fi
mkdir -p vllm_baseline/runtime_kvfabric_0221/jobs
cat > vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.sh <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd "\${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
exec "\${REMOTE_VENV:-.venv_kvfabric_0221}/bin/python" -m streamlit run \
  experiments/long_pressure_benchmark/dashboard/run_kvfabric_dashboard.py \
  --server.address 127.0.0.1 \
  --server.port "\${DASHBOARD_PORT:-8501}" \
  -- \
  --run-root "\${REMOTE_RUN_ROOT}" \
  --job-log "\${REMOTE_JOB_LOG:-}" \
  --refresh-seconds "\${DASHBOARD_REFRESH_SECONDS:-5}"
RUN
chmod +x vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.sh
pkill -f "streamlit run experiments/long_pressure_benchmark/dashboard/run_kvfabric_dashboard.py" 2>/dev/null || true
REMOTE_PROJECT="$REMOTE_PROJECT" \
REMOTE_VENV="$REMOTE_VENV" \
REMOTE_RUN_ROOT="\$REMOTE_RUN_ROOT" \
REMOTE_JOB_LOG="$REMOTE_JOB_LOG" \
DASHBOARD_PORT="$DASHBOARD_PORT" \
nohup bash vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.sh \
  > vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.log 2>&1 &
echo \$! > vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.pid
echo "dashboard_pid=\$(cat vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_dashboard.pid)"
echo "remote_url=http://127.0.0.1:$DASHBOARD_PORT"
echo "ssh_forward=ssh -L $DASHBOARD_PORT:127.0.0.1:$DASHBOARD_PORT $REMOTE_SSH_TARGET"
echo "run_root=\$REMOTE_RUN_ROOT"
REMOTE
