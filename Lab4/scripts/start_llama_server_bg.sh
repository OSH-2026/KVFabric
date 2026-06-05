#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/qy-dream/OSH_Project/KVFabric}"
BIN="${BIN:?set BIN to llama-server path}"
MODEL="${MODEL:?set MODEL to GGUF model path}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-18080}"
THREADS="${THREADS:-8}"
CTX_SIZE="${CTX_SIZE:-2048}"
PARALLEL="${PARALLEL:-2}"
LOG="${LOG:-$ROOT/Lab4/results/ray/llama_server_${PORT}.log}"
PID_FILE="${PID_FILE:-$ROOT/Lab4/runtime/logs/llama_server_${PORT}.pid}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
EXTRA_ARGS=("$@")

mkdir -p "$(dirname "$LOG")" "$(dirname "$PID_FILE")"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "llama-server already running: pid=$(cat "$PID_FILE") port=$PORT"
else
  nohup "$BIN" \
    -m "$MODEL" \
    --host "$HOST" \
    --port "$PORT" \
    --threads "$THREADS" \
    --ctx-size "$CTX_SIZE" \
    --parallel "$PARALLEL" \
    --no-webui \
    "${EXTRA_ARGS[@]}" \
    > "$LOG" 2>&1 &
  echo $! > "$PID_FILE"
  echo "llama-server starting: pid=$(cat "$PID_FILE") port=$PORT"
fi

deadline=$((SECONDS + TIMEOUT_SECONDS))
while [ "$SECONDS" -lt "$deadline" ]; do
  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "llama-server exited early; see $LOG" >&2
    tail -80 "$LOG" >&2 || true
    exit 1
  fi
  if curl -fsS "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    echo "llama-server ready: http://${HOST}:${PORT}"
    exit 0
  fi
  sleep 2
done

echo "llama-server did not become healthy within ${TIMEOUT_SECONDS}s; see $LOG" >&2
tail -80 "$LOG" >&2 || true
exit 1
