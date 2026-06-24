#!/usr/bin/env bash
set -euo pipefail

cd /home/zhoujiarun/KVFabric

.venv_kvfabric_0221/bin/python - <<'PY'
import importlib.util
import json
from pathlib import Path
from transformers import AutoTokenizer

cfg_path = Path("experiments/prebenchmark_validation/configs/cache_pressure_hot_revisit_27b_pressure.json")
spec = importlib.util.spec_from_file_location(
    "online_batch", "experiments/prebenchmark_validation/examples/online_batch.py")
online_batch = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(online_batch)

config = json.loads(cfg_path.read_text(encoding="utf-8"))
requests = online_batch.expand_requests(config)
tokenizer = AutoTokenizer.from_pretrained(".cache/models/Qwen3.5-27B-FP8")
lengths = []
for item in requests:
    text = tokenizer.apply_chat_template(
        item["messages"], tokenize=False, add_generation_prompt=True)
    lengths.append(len(tokenizer(text, add_special_tokens=False).input_ids))

print("requests", len(requests))
print("min", min(lengths), "max", max(lengths), "avg", sum(lengths) / len(lengths))
print("over_2048", sum(1 for value in lengths if value > 2048))
print("over_1800", sum(1 for value in lengths if value > 1800))
PY
