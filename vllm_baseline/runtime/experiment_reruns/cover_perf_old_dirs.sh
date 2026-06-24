#!/usr/bin/env bash
set -euo pipefail

cd /home/qy-dream/OSH_Project/KVFabric

src="$PWD/experiments/paper_reproductions/vllm_performance_benchmark/runs/2026-06-09_075429_qwen3_5_2b_perf_suite"

for name in \
  2026-05-01_151612_qwen3_5_2b_perf_suite \
  2026-05-01_160156_qwen3_5_2b_perf_suite; do
  dst="$PWD/experiments/paper_reproductions/vllm_performance_benchmark/runs/$name"
  case "$dst" in
    "$PWD"/experiments/paper_reproductions/vllm_performance_benchmark/runs/2026-05-01_*) ;;
    *) echo "Refusing unexpected target: $dst" >&2; exit 2 ;;
  esac

  mkdir -p "$dst"
  rsync -a --delete "$src/" "$dst/"

  python3 - "$dst" "$name" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
run_name = sys.argv[2]
source_name = "2026-06-09_075429_qwen3_5_2b_perf_suite"
source_abs = str(run_dir.parent / source_name)
target_abs = str(run_dir)

md = run_dir / "suite_summary.md"
if md.exists():
    text = md.read_text(encoding="utf-8")
    text = text.replace(source_name, run_name).replace(source_abs, target_abs)
    md.write_text(text, encoding="utf-8")

js = run_dir / "suite_summary.json"
if js.exists():
    data = json.loads(js.read_text(encoding="utf-8-sig"))
    if isinstance(data.get("run_group"), str):
        data["run_group"] = data["run_group"].replace(source_name, run_name)
    js.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8")
PY

  echo "updated $dst"
done
