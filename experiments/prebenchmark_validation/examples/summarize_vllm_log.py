from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PREFIX_RATE_RE = re.compile(r"Prefix cache hit rate: ([0-9.]+)%")
PROMPT_TPUT_RE = re.compile(r"Avg prompt throughput: ([0-9.]+) tokens/s")
GEN_TPUT_RE = re.compile(r"Avg generation throughput: ([0-9.]+) tokens/s")
KV_USAGE_RE = re.compile(r"GPU KV cache usage: ([0-9.]+)%")
ENABLE_PREFIX_RE = re.compile(r"enable_prefix_caching=(True|False)")
KV_SIZE_RE = re.compile(r"GPU KV cache size: ([0-9,]+) tokens")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize useful vLLM log fields.")
    parser.add_argument("log_file", help="Path to a vLLM server log file.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def last_float(pattern: re.Pattern[str], text: str) -> float | None:
    matches = pattern.findall(text)
    return float(matches[-1]) if matches else None


def main() -> None:
    args = parse_args()
    log_path = Path(args.log_file).expanduser().resolve()
    text = log_path.read_text(encoding="utf-8", errors="replace")

    enabled_matches = ENABLE_PREFIX_RE.findall(text)
    kv_size_matches = KV_SIZE_RE.findall(text)
    summary = {
        "log_file": str(log_path),
        "enable_prefix_caching_last": enabled_matches[-1]
        if enabled_matches
        else None,
        "prefix_cache_hit_rate_last": last_float(PREFIX_RATE_RE, text),
        "avg_prompt_throughput_last": last_float(PROMPT_TPUT_RE, text),
        "avg_generation_throughput_last": last_float(GEN_TPUT_RE, text),
        "gpu_kv_cache_usage_last": last_float(KV_USAGE_RE, text),
        "gpu_kv_cache_size_tokens_last": int(kv_size_matches[-1].replace(",", ""))
        if kv_size_matches
        else None,
        "prefix_cache_rate_samples": [float(item) for item in PREFIX_RATE_RE.findall(text)],
    }

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()

