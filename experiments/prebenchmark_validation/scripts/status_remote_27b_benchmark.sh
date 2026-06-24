#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

REMOTE_HOST="${REMOTE_HOST:-robowalker}"
REMOTE_SSH_TARGET="${REMOTE_SSH_TARGET:-$REMOTE_HOST}"
REMOTE_SSH_OPTS="${REMOTE_SSH_OPTS:-}"
REMOTE_PROJECT="${REMOTE_PROJECT:-/home/zhoujiarun/KVFabric}"
REMOTE_RUN_PATTERN="${REMOTE_RUN_PATTERN:-*qwen3_5_27b_realistic_10h_pressure_long}"
REMOTE_RUN_ROOT="${REMOTE_RUN_ROOT:-}"
REMOTE_JOB_LOG="${REMOTE_JOB_LOG:-vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_realistic_10h.log}"
TAIL_LINES="${TAIL_LINES:-80}"
REMOTE_PYTHON="${REMOTE_PYTHON:-python3}"

load_common_env

ssh $REMOTE_SSH_OPTS "$REMOTE_SSH_TARGET" \
  "REMOTE_PROJECT='$REMOTE_PROJECT' REMOTE_RUN_ROOT='$REMOTE_RUN_ROOT' REMOTE_RUN_PATTERN='$REMOTE_RUN_PATTERN' REMOTE_JOB_LOG='$REMOTE_JOB_LOG' TAIL_LINES='$TAIL_LINES' REMOTE_PYTHON='$REMOTE_PYTHON' bash -s" <<'REMOTE'
set -euo pipefail
cd "$REMOTE_PROJECT"

if [[ -z "$REMOTE_RUN_ROOT" ]]; then
  REMOTE_RUN_ROOT=$(find experiments/prebenchmark_validation/runs \
    -maxdepth 1 -type d -name "$REMOTE_RUN_PATTERN" | sort | tail -n 1 || true)
fi

echo "--- wall clock ---"
date '+%F %T %Z'
echo
echo "--- remote run root ---"
if [[ -n "$REMOTE_RUN_ROOT" ]]; then
  echo "$REMOTE_PROJECT/$REMOTE_RUN_ROOT"
else
  echo "No run root matched pattern: $REMOTE_RUN_PATTERN"
fi
echo

echo "--- job log tail ---"
tail -n "$TAIL_LINES" "$REMOTE_JOB_LOG" 2>/dev/null || true
echo

echo "--- gpu ---"
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,clocks.sm \
  --format=csv,noheader 2>/dev/null || true
echo

echo "--- processes ---"
ps -ef | grep -E 'realistic_10h|trace_12h|trace_long|run_remote_27b_long|run_remote_27b_trace|vllm serve|online_duration|online_trace' | grep -v grep || true
echo

if [[ -z "$REMOTE_RUN_ROOT" || ! -d "$REMOTE_RUN_ROOT" ]]; then
  exit 0
fi

echo "--- policy summaries ---"
"$REMOTE_PYTHON" - "$REMOTE_RUN_ROOT" <<'PY' || true
import json
import sys
from pathlib import Path

run_root = Path(sys.argv[1])
policies = ["lru", "shared_aware", "family_protect"]

def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def latest_jsonl(path: Path):
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    return json.loads(last) if last else None

for policy in policies:
    policy_dir = run_root / policy
    online_dir = policy_dir / "online_trace"
    if not online_dir.exists():
        online_dir = policy_dir / "online_duration"
    metrics = load_json(online_dir / "metrics.json")
    lifecycle = load_json(policy_dir / "kvfabric_lifecycle_metrics.json")
    rolling = latest_jsonl(online_dir / "rolling_metrics.jsonl")
    source = metrics or rolling
    if source is None:
        print(f"{policy}: pending")
        continue
    fields = [
        f"completed={source.get('completed', 0)}",
        f"errors={source.get('errors', 0)}",
        f"rps={source.get('requests_per_second', 0.0):.4f}",
        f"total_tok_s={source.get('total_tokens_per_second', 0.0):.2f}",
        f"lat_avg={source.get('latency_avg_seconds', 0.0):.3f}",
        f"lat_p95={source.get('latency_p95_seconds', 0.0):.3f}",
        f"elapsed={source.get('elapsed_seconds', source.get('total_seconds', 0.0)):.1f}",
    ]
    if lifecycle:
        fields.extend([
            f"prefix_hit={lifecycle.get('prefix_hit_rate', 0.0):.4f}",
            f"rebuilt={lifecycle.get('rebuilt_from_eviction_blocks', 0)}",
            f"regret={lifecycle.get('regretful_eviction_proxy_rate', 0.0):.4f}",
            f"evicted={lifecycle.get('evicted_blocks', 0)}",
            f"admit_limited={lifecycle.get('cache_admission_limited_events', 0)}",
            f"admit_saved={lifecycle.get('cache_admission_saved_blocks', 0)}",
            f"deferred={lifecycle.get('request_deferred_events', 0)}",
        ])
    print(f"{policy}: " + " ".join(fields))
    class_metrics = source.get("class_metrics") or {}
    for request_class, item in sorted(class_metrics.items()):
        print(
            f"  class={request_class} completed={item.get('completed', 0)} "
            f"errors={item.get('errors', 0)} "
            f"tok_s={item.get('total_tokens_per_second', 0.0):.2f} "
            f"lat_avg={item.get('latency_avg_seconds', 0.0):.3f} "
            f"lat_p95={item.get('latency_p95_seconds', 0.0):.3f}"
        )
PY
echo

echo "--- run size ---"
du -sh "$REMOTE_RUN_ROOT" 2>/dev/null || true
REMOTE
