#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/KVFabric_Lab4_runtime}"
RUNS="${RUNS:-5}"
PROMPT_FILE="${PROMPT_FILE:-$ROOT/prompts/single_short.txt}"
MODEL="${MODEL:-$ROOT/models/model.gguf}"
BIN="${BIN:-$ROOT/src/llama.cpp/build-cuda-rpc/bin/llama-completion}"
SCRIPT="${SCRIPT:-$ROOT/scripts/run_completion_repeats.sh}"
OUT_ROOT="${OUT_ROOT:-$ROOT/results/tuning}"

run_case() {
  local name="$1"
  local threads="$2"
  local ctx="$3"
  shift 3
  echo "### tuning case: $name"
  THREADS="$threads" CTX_SIZE="$ctx" N_PREDICT=64 TEMP=0.2 \
    bash "$SCRIPT" "$BIN" "$MODEL" "$PROMPT_FILE" "$OUT_ROOT/$name" "$RUNS" "$name" "$@"
}

run_case A_gpu_t8_ctx2048 8 2048 --n-gpu-layers 99
run_case B_gpu_t4_ctx2048 4 2048 --n-gpu-layers 99
run_case C_gpu_t16_ctx2048 16 2048 --n-gpu-layers 99
run_case D_gpu_t8_batch256 8 2048 --batch-size 256 --n-gpu-layers 99
run_case E_gpu_t8_batch512 8 2048 --batch-size 512 --n-gpu-layers 99
run_case F_gpu_t8_ctx4096 8 4096 --n-gpu-layers 99
run_case G_cpu_t8_ctx2048 8 2048 --n-gpu-layers 0
run_case H_gpu_t8_no_mmap 8 2048 --no-mmap --n-gpu-layers 99
run_case I_gpu_t8_batch1024 8 2048 --batch-size 1024 --n-gpu-layers 99
run_case J_gpu_t8_ctx8192 8 8192 --n-gpu-layers 99
