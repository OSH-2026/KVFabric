from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare KVFabric A/B metrics.")
    parser.add_argument("run_dir", help="A/B run directory with lru/shared_aware.")
    parser.add_argument("--candidate", default="family_protect")
    parser.add_argument("--output", help="Optional Markdown output path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def reduction_percent(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (old - new) / old * 100.0


def increase_percent(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def metric(payload: dict[str, Any], name: str, default: float = 0.0) -> float:
    return float(payload.get(name, default))


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    lru_lifecycle = read_json(run_dir / "lru" / "kvfabric_lifecycle_metrics.json")
    kv_lifecycle = read_json(run_dir / args.candidate / "kvfabric_lifecycle_metrics.json")
    lru_online = read_json(run_dir / "lru" / "online" / "metrics.json")
    kv_online = read_json(run_dir / args.candidate / "online" / "metrics.json")
    lru_prom = read_json_if_exists(run_dir / "lru" / "prometheus_metrics_summary.json")
    kv_prom = read_json_if_exists(
        run_dir / args.candidate / "prometheus_metrics_summary.json"
    )

    retain_reduction = reduction_percent(
        float(lru_lifecycle["avg_evicted_retain_score"]),
        float(kv_lifecycle["avg_evicted_retain_score"]),
    )
    shared_anchor_reduction = reduction_percent(
        float(lru_lifecycle["shared_anchor_eviction_ratio"]),
        float(kv_lifecycle["shared_anchor_eviction_ratio"]),
    )
    evicted_reduction = reduction_percent(
        float(lru_lifecycle["evicted_blocks"]),
        float(kv_lifecycle["evicted_blocks"]),
    )
    protected_eviction_reduction = reduction_percent(
        metric(lru_lifecycle, "protected_eviction_ratio"),
        metric(kv_lifecycle, "protected_eviction_ratio"),
    )
    selected_protected_reduction = reduction_percent(
        metric(lru_lifecycle, "ranking_selected_protected_ratio"),
        metric(kv_lifecycle, "ranking_selected_protected_ratio"),
    )
    throughput_delta = increase_percent(
        float(lru_online["requests_per_second"]),
        float(kv_online["requests_per_second"]),
    )
    metadata_overhead_delta = increase_percent(
        metric(lru_prom, "kv_metadata_update_time_seconds_avg"),
        metric(kv_prom, "kv_metadata_update_time_seconds_avg"),
    )
    lookup_overhead_delta = increase_percent(
        metric(lru_prom, "kv_block_lookup_time_seconds_avg"),
        metric(kv_prom, "kv_block_lookup_time_seconds_avg"),
    )

    lines = [
        "# KVFabric A/B Comparison",
        "",
        f"- Run: `{run_dir}`",
        f"- Candidate policy: `{args.candidate}`",
        f"- Avg evicted retain score: "
        f"{lru_lifecycle['avg_evicted_retain_score']:.4f} -> "
        f"{kv_lifecycle['avg_evicted_retain_score']:.4f} "
        f"({retain_reduction:.2f}% reduction)",
        f"- Shared-anchor eviction ratio: "
        f"{lru_lifecycle['shared_anchor_eviction_ratio']:.6f} -> "
        f"{kv_lifecycle['shared_anchor_eviction_ratio']:.6f} "
        f"({shared_anchor_reduction:.2f}% reduction)",
        f"- Evicted blocks: {lru_lifecycle['evicted_blocks']} -> "
        f"{kv_lifecycle['evicted_blocks']} ({evicted_reduction:.2f}% reduction)",
        f"- Protected eviction ratio: "
        f"{metric(lru_lifecycle, 'protected_eviction_ratio'):.6f} -> "
        f"{metric(kv_lifecycle, 'protected_eviction_ratio'):.6f} "
        f"({protected_eviction_reduction:.2f}% reduction)",
        f"- Ranking selected protected ratio: "
        f"{metric(lru_lifecycle, 'ranking_selected_protected_ratio'):.6f} -> "
        f"{metric(kv_lifecycle, 'ranking_selected_protected_ratio'):.6f} "
        f"({selected_protected_reduction:.2f}% reduction)",
        f"- Admission saved blocks: "
        f"{int(metric(lru_lifecycle, 'cache_admission_saved_blocks'))} -> "
        f"{int(metric(kv_lifecycle, 'cache_admission_saved_blocks'))}",
        f"- Admission saved ratio: "
        f"{metric(lru_lifecycle, 'cache_admission_saved_ratio'):.6f} -> "
        f"{metric(kv_lifecycle, 'cache_admission_saved_ratio'):.6f}",
        f"- Prefix hit rate: {lru_lifecycle['prefix_hit_rate']:.6f} -> "
        f"{kv_lifecycle['prefix_hit_rate']:.6f}",
        f"- Requests/s: {lru_online['requests_per_second']:.4f} -> "
        f"{kv_online['requests_per_second']:.4f} "
        f"({throughput_delta:.2f}% change)",
        "",
        "## Prometheus Probe Metrics",
        "",
        f"- Request hit rate: "
        f"{metric(lru_prom, 'request_hit_rate'):.6f} -> "
        f"{metric(kv_prom, 'request_hit_rate'):.6f}",
        f"- Prefix token hit rate: "
        f"{metric(lru_prom, 'prefix_token_hit_rate'):.6f} -> "
        f"{metric(kv_prom, 'prefix_token_hit_rate'):.6f}",
        f"- Saved prefill tokens proxy: "
        f"{int(metric(lru_prom, 'saved_prefill_tokens_proxy'))} -> "
        f"{int(metric(kv_prom, 'saved_prefill_tokens_proxy'))}",
        f"- Recompute ratio proxy: "
        f"{metric(lru_prom, 'recompute_ratio_proxy'):.6f} -> "
        f"{metric(kv_prom, 'recompute_ratio_proxy'):.6f}",
        f"- KV block lookup hit rate: "
        f"{metric(lru_prom, 'kv_block_lookup_hit_rate'):.6f} -> "
        f"{metric(kv_prom, 'kv_block_lookup_hit_rate'):.6f}",
        f"- KV block reuse/allocation proxy: "
        f"{metric(lru_prom, 'kv_block_reuse_per_allocation_proxy'):.6f} -> "
        f"{metric(kv_prom, 'kv_block_reuse_per_allocation_proxy'):.6f}",
        f"- KV cache usage avg: "
        f"{metric(lru_prom, 'kv_cache_usage_perc_avg'):.6f} -> "
        f"{metric(kv_prom, 'kv_cache_usage_perc_avg'):.6f}",
        f"- Memory headroom proxy: "
        f"{metric(lru_prom, 'memory_headroom_proxy'):.6f} -> "
        f"{metric(kv_prom, 'memory_headroom_proxy'):.6f}",
        f"- TTFT avg seconds: "
        f"{metric(lru_prom, 'ttft_seconds_avg'):.6f} -> "
        f"{metric(kv_prom, 'ttft_seconds_avg'):.6f}",
        f"- TPOT avg seconds: "
        f"{metric(lru_prom, 'tpot_seconds_avg'):.6f} -> "
        f"{metric(kv_prom, 'tpot_seconds_avg'):.6f}",
        f"- E2E latency avg seconds: "
        f"{metric(lru_prom, 'e2e_latency_seconds_avg'):.6f} -> "
        f"{metric(kv_prom, 'e2e_latency_seconds_avg'):.6f}",
        f"- KV block recompute cost avg tokens: "
        f"{metric(lru_prom, 'kv_block_recompute_cost_tokens_avg'):.6f} -> "
        f"{metric(kv_prom, 'kv_block_recompute_cost_tokens_avg'):.6f}",
        f"- KV block eviction regret rate: "
        f"{metric(lru_prom, 'kv_block_eviction_regret_rate'):.6f} -> "
        f"{metric(kv_prom, 'kv_block_eviction_regret_rate'):.6f}",
        f"- Metadata update time avg seconds: "
        f"{metric(lru_prom, 'kv_metadata_update_time_seconds_avg'):.9f} -> "
        f"{metric(kv_prom, 'kv_metadata_update_time_seconds_avg'):.9f} "
        f"({metadata_overhead_delta:.2f}% change)",
        f"- KV lookup time avg seconds: "
        f"{metric(lru_prom, 'kv_block_lookup_time_seconds_avg'):.9f} -> "
        f"{metric(kv_prom, 'kv_block_lookup_time_seconds_avg'):.9f} "
        f"({lookup_overhead_delta:.2f}% change)",
        "",
        "Interpretation: KVFabric improves eviction quality, not raw throughput "
        "in this Python-layer prototype.",
    ]
    payload = "\n".join(lines) + "\n"

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
