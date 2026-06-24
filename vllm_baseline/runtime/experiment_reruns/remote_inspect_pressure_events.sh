#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric
run_dir=/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_091819_qwen3_5_27b_cache_pressure_hot_revisit_27b_pressure_kvfabric_ab

echo "--- files ---"
find "$run_dir" -maxdepth 3 -type f | sort | sed -n '1,220p'

for policy in lru shared_aware family_protect; do
  log="$run_dir/$policy/kvfabric_lifecycle.jsonl"
  metrics="$run_dir/$policy/kvfabric_lifecycle_metrics.json"
  echo "--- $policy metrics ---"
  python3 - "$metrics" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text()) if p.exists() else {}
for key in [
    "evicted_blocks", "sealed_blocks", "touched_blocks",
    "eviction_ranking_events", "eviction_policies",
    "prefix_hit_rate", "prefix_hit_tokens",
    "tail_eviction_ratio", "avg_evicted_retain_score",
    "avg_selected_retain_score",
]:
    print(key, data.get(key))
print("events", data.get("events"))
PY
  echo "--- $policy event counts/sample ---"
  python3 - "$log" <<'PY'
import collections
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
counts = collections.Counter()
samples = {}
policy_values = collections.Counter()
if p.exists():
    with p.open() as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            event = obj.get("event")
            counts[event] += 1
            samples.setdefault(event, obj)
            if "policy" in obj:
                policy_values[obj.get("policy")] += 1
print("counts", dict(counts))
print("policy_values", dict(policy_values))
for name in [
    "eviction_candidates_ranked",
    "block_evicted",
    "block_sealed",
    "block_touched",
]:
    if name in samples:
        print(name, json.dumps(samples[name], ensure_ascii=False)[:1200])
PY
done
