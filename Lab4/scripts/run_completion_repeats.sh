#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 6 ]; then
  echo "usage: $0 <llama-completion> <model> <prompt-file> <out-dir> <runs> <label> [extra args...]" >&2
  exit 2
fi

BIN="$1"
MODEL="$2"
PROMPT_FILE="$3"
OUT_DIR="$4"
RUNS="$5"
LABEL="$6"
shift 6
EXTRA_ARGS=("$@")

N_PREDICT="${N_PREDICT:-64}"
THREADS="${THREADS:-8}"
CTX_SIZE="${CTX_SIZE:-2048}"
TEMP="${TEMP:-0.2}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"

mkdir -p "$OUT_DIR"

for i in $(seq 1 "$RUNS"); do
  LOG="$OUT_DIR/run_${i}.log"
  echo "=== ${LABEL} run ${i} ==="
  timeout "$TIMEOUT_SECONDS" /usr/bin/time -v "$BIN" \
    -m "$MODEL" \
    -f "$PROMPT_FILE" \
    -n "$N_PREDICT" \
    -no-cnv \
    --threads "$THREADS" \
    --ctx-size "$CTX_SIZE" \
    --temp "$TEMP" \
    --no-display-prompt \
    "${EXTRA_ARGS[@]}" \
    2>&1 | tee "$LOG" >/dev/null

  grep -E 'common_perf_print|Maximum resident|Elapsed|Exit status' "$LOG" || true
done
