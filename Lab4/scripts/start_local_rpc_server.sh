#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/qy-dream/OSH_Project/KVFabric}"
BIN="${BIN:-$ROOT/Lab4/runtime/src/llama.cpp/build-cpu-rpc/bin/rpc-server}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-50052}"
THREADS="${THREADS:-8}"
LOG="${LOG:-$ROOT/Lab4/results/rpc/local_rpc_server_${PORT}.log}"
PID_FILE="${PID_FILE:-$ROOT/Lab4/runtime/logs/local_rpc_server_${PORT}.pid}"

mkdir -p "$(dirname "$LOG")" "$(dirname "$PID_FILE")"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "rpc-server already running: pid=$(cat "$PID_FILE")"
  exit 0
fi

nohup "$BIN" -H "$HOST" -p "$PORT" -t "$THREADS" > "$LOG" 2>&1 &
echo $! > "$PID_FILE"

sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "rpc-server failed to start; see $LOG" >&2
  exit 1
fi

echo "rpc-server started: pid=$(cat "$PID_FILE") host=$HOST port=$PORT"
grep -E "listening|Starting|error|ERR|rpc" "$LOG" | tail -20 || true
