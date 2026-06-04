from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Any


def scrape_metrics(metrics_url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch Prometheus metrics from vLLM and parse KV-cache-related gauges/counters.

    Returns a flat dict of numeric values. Returns {} on failure.
    """
    try:
        req = urllib.request.Request(metrics_url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {}

    return _parse_prometheus(payload)


def _parse_prometheus(text: str) -> dict[str, Any]:
    """Extract KV-related metrics from Prometheus text format."""
    metrics: dict[str, Any] = {}
    counters: dict[str, float] = {}
    gauges: dict[str, float] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # gauge / counter lines: name{labels} value  OR  name value
        try:
            if "{" in line:
                name_end = line.index("{")
                label_end = line.index("}", name_end)
                name = line[:name_end]
                value_str = line[label_end + 1:].strip().split()[0]
            else:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[0]
                value_str = parts[1]

            value = float(value_str)
        except (ValueError, IndexError):
            continue

        if name.endswith("_created"):
            continue  # skip timestamp fields
        if name.endswith(("_total", "_sum", "_count")):
            # Counter or histogram component
            base = name.rsplit("_", 1)[0]
            if base not in counters:
                counters[base] = 0.0
            counters[base] += value
        else:
            # Gauge
            gauges[name] = value

    # Merge: prefer gauges, then counters
    metrics.update(gauges)
    metrics.update(counters)

    # Extract key KVFabric metrics
    return {
        "kv_cache_usage_perc": _gauge(gauges, "vllm:kv_cache_usage_perc"),
        "kv_block_free": _gauge(gauges, "vllm:kv_block_free"),
        "kv_block_total": _gauge(gauges, "vllm:kv_block_total"),
        "kv_block_active": _gauge(gauges, "vllm:kv_block_active"),
        "kv_block_peak_active": _gauge(gauges, "vllm:kv_block_peak_active"),
        "prefix_cache_hit_rate": _ratio(
            _counter(counters, "vllm:prefix_cache_hits"),
            _counter(counters, "vllm:prefix_cache_queries"),
        ),
        "kv_block_lookup_hit_rate": _ratio(
            _counter(counters, "vllm:kv_block_lookup_hits"),
            _counter(counters, "vllm:kv_block_lookup_queries"),
        ),
        "kv_block_evictions": _counter(counters, "vllm:kv_block_evictions"),
        "kv_block_eviction_regrets": _counter(counters, "vllm:kv_block_eviction_regrets"),
        "eviction_regret_rate": _ratio(
            _counter(counters, "vllm:kv_block_eviction_regrets"),
            _counter(counters, "vllm:kv_block_evictions"),
        ),
        "prompt_tokens_total": _counter(counters, "vllm:prompt_tokens"),
        "prompt_tokens_cached": _counter(counters, "vllm:prompt_tokens_cached"),
        "prompt_tokens_recomputed": _counter(counters, "vllm:prompt_tokens_recomputed"),
        "running_requests": _gauge(gauges, "vllm:num_requests_running"),
        "waiting_requests": _gauge(gauges, "vllm:num_requests_waiting"),
    }


def _gauge(gauges: dict, name: str) -> float:
    return gauges.get(name, 0.0)


def _counter(counters: dict, base_name: str) -> float:
    return counters.get(base_name, 0.0)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


class MetricsSnapshotCollector:
    """Periodically collects vLLM Prometheus metrics snapshots."""

    def __init__(self, metrics_url: str, output_dir: Path):
        self.metrics_url = metrics_url
        self.output_path = output_dir / "kv_metrics_snapshots.jsonl"
        self._file = None

    def open(self) -> None:
        self._file = self.output_path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._file:
            self._file.close()

    def collect(self, round_num: int) -> dict[str, Any]:
        """Scrape and record a single metrics snapshot."""
        import json

        snapshot = scrape_metrics(self.metrics_url)
        snapshot["round"] = round_num
        snapshot["timestamp"] = time.time()

        if self._file:
            self._file.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
            if round_num % 10 == 0:
                self._file.flush()

        return snapshot
