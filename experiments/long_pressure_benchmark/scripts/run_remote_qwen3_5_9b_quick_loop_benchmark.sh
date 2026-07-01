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
REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-remote_qwen3_5_9b_quick_loop}"
QUICK_MODULE="${KVFABRIC_QWEN9B_QUICK_MODULE:-${1:-throughput}}"
QUICK_CAPACITY="${KVFABRIC_QWEN9B_QUICK_CAPACITY:-${2:-medium}}"
QUICK_POLICIES="${KVFABRIC_QWEN9B_QUICK_POLICIES:-}"

load_common_env

ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_PROJECT"
mkdir -p vllm_baseline/runtime_kvfabric_0221/jobs
bash vllm_baseline/scripts/stop_server.sh qwen3_5_9b || true

job_name="${REMOTE_JOB_NAME}_${QUICK_MODULE}_${QUICK_CAPACITY}_\$(date +%Y%m%d_%H%M%S)"
job_script="vllm_baseline/runtime_kvfabric_0221/jobs/\${job_name}.sh"
job_log="vllm_baseline/runtime_kvfabric_0221/jobs/\${job_name}.log"
job_pid="vllm_baseline/runtime_kvfabric_0221/jobs/\${job_name}.pid"

cat > "\$job_script" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd "\${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"

export VLLM_VENV_DIR="\${REMOTE_VENV:-.venv_kvfabric_0221}"
export VLLM_SERVER_START_TIMEOUT="\${VLLM_SERVER_START_TIMEOUT:-900}"
export PRESET="\${PRESET:-qwen3_5_9b}"

bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh \\
  "\${KVFABRIC_QWEN9B_QUICK_MODULE:-throughput}" \\
  "\${KVFABRIC_QWEN9B_QUICK_CAPACITY:-medium}"
RUN

chmod +x "\$job_script"
REMOTE_PROJECT="$REMOTE_PROJECT" \\
REMOTE_VENV="$REMOTE_VENV" \\
PRESET="qwen3_5_9b" \\
KVFABRIC_QWEN9B_QUICK_MODULE="$QUICK_MODULE" \\
KVFABRIC_QWEN9B_QUICK_CAPACITY="$QUICK_CAPACITY" \\
KVFABRIC_QWEN9B_QUICK_POLICIES="$QUICK_POLICIES" \\
nohup bash "\$job_script" > "\$job_log" 2>&1 &
echo \$! > "\$job_pid"
ln -sf "\$(basename "\$job_log")" vllm_baseline/runtime_kvfabric_0221/jobs/remote_qwen3_5_9b_quick_loop_latest.log
ln -sf "\$(basename "\$job_pid")" vllm_baseline/runtime_kvfabric_0221/jobs/remote_qwen3_5_9b_quick_loop_latest.pid
echo "started_\${job_name}_pid=\$(cat "\$job_pid")"
echo "job_log=$REMOTE_PROJECT/\$job_log"
REMOTE
