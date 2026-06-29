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
REMOTE_JOB_NAME="${REMOTE_JOB_NAME:-remote_qwen3_5_9b_12h_matrix}"

load_common_env

ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_PROJECT"
mkdir -p vllm_baseline/runtime_kvfabric_0221/jobs
bash vllm_baseline/scripts/stop_server.sh qwen3_5_9b || true

cat > "vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd "\${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"

export VLLM_VENV_DIR="\${REMOTE_VENV:-.venv_kvfabric_0221}"
export VLLM_SERVER_START_TIMEOUT="\${VLLM_SERVER_START_TIMEOUT:-900}"
export PRESET="\${PRESET:-qwen3_5_9b}"

bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh
RUN

chmod +x "vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.sh"
REMOTE_PROJECT="$REMOTE_PROJECT" \
REMOTE_VENV="$REMOTE_VENV" \
PRESET="qwen3_5_9b" \
nohup bash "vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.sh" \
  > "vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.log" 2>&1 &
echo \$! > "vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.pid"
echo "started_${REMOTE_JOB_NAME}_pid=\$(cat vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.pid)"
echo "job_log=$REMOTE_PROJECT/vllm_baseline/runtime_kvfabric_0221/jobs/${REMOTE_JOB_NAME}.log"
REMOTE
