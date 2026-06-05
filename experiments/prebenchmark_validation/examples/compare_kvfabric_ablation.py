from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare KVFabric ablation metrics.")
    parser.add_argument("run_dir", help="Ablation run directory with variant subdirs.")
    parser.add_argument(
        "--variants",
        nargs="+",
        help="Variant order. Defaults to all subdirectories that contain metrics.",
    )
    parser.add_argument("--output", help="Optional Markdown output path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric(payload: dict[str, Any], name: str, default: float = 0.0) -> float:
    return float(payload.get(name, default))


def discover_variants(run_dir: Path) -> list[str]:
    variants = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "kvfabric_lifecycle_metrics.json").exists():
            variants.append(child.name)
    return variants


def row_for(run_dir: Path, variant: str) -> str:
    variant_dir = run_dir / variant
    lifecycle = read_json(variant_dir / "kvfabric_lifecycle_metrics.json")
    online = read_json(variant_dir / "online" / "metrics.json")
    prometheus = read_json(variant_dir / "prometheus_metrics_summary.json")
    return (
        f"| {variant} "
        f"| {int(metric(lifecycle, 'evicted_blocks'))} "
        f"| {metric(lifecycle, 'shared_anchor_eviction_ratio'):.6f} "
        f"| {int(metric(lifecycle, 'ranking_selected_protected_count'))} "
        f"| {int(metric(lifecycle, 'rebuilt_from_eviction_blocks'))} "
        f"| {metric(lifecycle, 'prefix_hit_rate'):.6f} "
        f"| {int(metric(lifecycle, 'prefix_hit_tokens'))} "
        f"| {metric(online, 'requests_per_second'):.4f} "
        f"| {metric(prometheus, 'ttft_seconds_avg'):.6f} "
        f"| {metric(prometheus, 'e2e_latency_seconds_avg'):.6f} |"
    )


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    variants = args.variants or discover_variants(run_dir)
    if not variants:
        raise SystemExit(f"No variant metrics found under {run_dir}")

    lines = [
        "# KVFabric Ablation Comparison",
        "",
        f"- Run: `{run_dir}`",
        "",
        "| Variant | Evicted | Shared-anchor | Selected protected | Rebuilt | "
        "Prefix hit rate | Hit tokens | Req/s | TTFT | E2E |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(row_for(run_dir, variant) for variant in variants)
    lines.extend(
        [
            "",
            "Interpretation: use lifecycle metrics to judge whether a factor changes "
            "eviction quality; request-level metrics are useful only when the run "
            "is stable enough to compare.",
        ]
    )
    payload = "\n".join(lines) + "\n"

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
