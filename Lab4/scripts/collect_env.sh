#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-Lab4/results/env}"
mkdir -p "$OUT_DIR"

{
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "whoami=$(whoami)"
  echo "pwd=$(pwd)"
  echo
  echo "## uname"
  uname -a || true
  echo
  echo "## os-release"
  cat /etc/os-release || true
  echo
  echo "## python"
  python3 --version || true
  echo
  echo "## cmake"
  cmake --version || true
  echo
  echo "## compiler"
  gcc --version || true
  g++ --version || true
  echo
  echo "## cpu"
  lscpu || true
  echo
  echo "## memory"
  free -h || true
  echo
  echo "## gpu"
  nvidia-smi || true
  echo
  echo "## disk"
  df -h . || true
} > "$OUT_DIR/local_env.txt" 2>&1

echo "wrote $OUT_DIR/local_env.txt"
