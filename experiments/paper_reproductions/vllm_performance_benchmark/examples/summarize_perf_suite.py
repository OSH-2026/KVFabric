"""
Summarize performance suite results across multiple variants.

Reads metrics.json from each variant subdirectory and produces:
- suite_summary.json (structured cross-variant comparison)
- suite_summary.md (human-readable report)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize a performance benchmark suite run across variants."
    )
    parser.add_argument(
        "run_group_dir",
        help="The top-level run group directory containing variant subdirectories.",
    )
    return parser.parse_args()


def load_variant_metrics(variant_dir: Path) -> dict | None:
    metrics_file = variant_dir / "metrics.json"
    if not metrics_file.exists():
        return None

    env_file = variant_dir / "env.json"
    env_data = {}
    if env_file.exists():
        env_data = json.loads(env_file.read_text(encoding="utf-8"))

    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    return {
        "variant_name": env_data.get("variant_name", variant_dir.name),
        "variant_description": env_data.get("variant_description", ""),
        "enable_prefix_caching": env_data.get("enable_prefix_caching"),
        "metrics": metrics,
    }


def compute_scan_summary(metrics: list[dict]) -> dict:
    successful = [m for m in metrics if m.get("success")]
    if not successful:
        return {"successful_points": 0, "total_points": len(metrics)}

    return {
        "successful_points": len(successful),
        "total_points": len(metrics),
        "avg_request_throughput": sum(m.get("request_throughput", 0) for m in successful) / len(successful),
        "avg_total_token_throughput": sum(m.get("total_token_throughput", 0) for m in successful) / len(successful),
        "avg_output_token_throughput": sum(m.get("output_token_throughput", 0) for m in successful) / len(successful),
        "peak_kv_cache_usage_pct": max((m.get("kv_cache_usage_pct", 0) for m in successful), default=0),
        "kv_cache_capacity_tokens": max((m.get("kv_cache_tokens", 0) for m in successful), default=0),
    }


def main() -> None:
    args = parse_args()
    run_group = Path(args.run_group_dir).expanduser().resolve()

    if not run_group.is_dir():
        print(f"Not a directory: {run_group}")
        return

    # Find variant subdirectories (directories containing metrics.json)
    variants = {}
    for d in sorted(run_group.iterdir()):
        if d.is_dir():
            vm = load_variant_metrics(d)
            if vm is not None:
                variants[d.name] = vm

    if not variants:
        print(f"No variant metrics found in {run_group}")
        return

    # Designate first variant as baseline
    variant_names = sorted(variants.keys())
    baseline_name = variant_names[0]
    baseline = variants[baseline_name]
    baseline_summary = compute_scan_summary(baseline["metrics"])

    # Build suite summary JSON
    suite_data = {
        "run_group": str(run_group),
        "baseline_variant": baseline_name,
        "baseline_summary": baseline_summary,
        "variants": {},
    }

    for vname in variant_names:
        v = variants[vname]
        vs = compute_scan_summary(v["metrics"])

        # Compute deltas vs baseline
        if baseline_summary.get("avg_request_throughput", 0) > 0:
            req_delta = (
                (vs.get("avg_request_throughput", 0) - baseline_summary["avg_request_throughput"])
                / baseline_summary["avg_request_throughput"]
                * 100
            )
            tok_delta = (
                (vs.get("avg_total_token_throughput", 0) - baseline_summary["avg_total_token_throughput"])
                / baseline_summary["avg_total_token_throughput"]
                * 100
            )
        else:
            req_delta = 0.0
            tok_delta = 0.0

        suite_data["variants"][vname] = {
            "variant_name": v["variant_name"],
            "variant_description": v["variant_description"],
            "summary": vs,
            "delta_vs_baseline": {
                "request_throughput_pct": round(req_delta, 1),
                "total_token_throughput_pct": round(tok_delta, 1),
            },
        }

    # Save JSON
    (run_group / "suite_summary.json").write_text(
        json.dumps(suite_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build Markdown report
    lines = [
        "# Performance Suite Summary",
        "",
        f"Run group: `{run_group.name}`",
        f"Baseline: **{baseline_name}** ({baseline['variant_description']})",
        "",
        "## Variant Comparison",
        "",
        "| Variant | Req/s | Total tok/s | Out tok/s | KV Peak% | vs Baseline (req) | vs Baseline (tok) |",
        "|:--------|:-----:|:----------:|:---------:|:--------:|:-----------------:|:-----------------:|",
    ]

    for vname in variant_names:
        v = suite_data["variants"][vname]
        s = v["summary"]
        d = v["delta_vs_baseline"]
        lines.append(
            f"| {vname} | {s.get('avg_request_throughput', 0):.2f} | "
            f"{s.get('avg_total_token_throughput', 0):.2f} | "
            f"{s.get('avg_output_token_throughput', 0):.2f} | "
            f"{s.get('peak_kv_cache_usage_pct', 0):.1f}% | "
            f"{d['request_throughput_pct']:+.1f}% | "
            f"{d['total_token_throughput_pct']:+.1f}% |"
        )

    lines += [
        "",
        "## Per-Variant Details",
        "",
    ]

    for vname in variant_names:
        v = variants[vname]
        lines += [
            f"### {vname}",
            f"_{v['variant_description']}_",
            "",
        ]
        if v.get("enable_prefix_caching") is True:
            lines.append("- Prefix caching: **ON**")
        elif v.get("enable_prefix_caching") is False:
            lines.append("- Prefix caching: **OFF**")

        m = v["metrics"]
        successful = [x for x in m if x.get("success")]
        lines.append(f"- Successful: {len(successful)}/{len(m)} points")
        lines.append("")

        if successful:
            lines.append("| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |")
            lines.append("|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|")
            for x in m:
                if x.get("success"):
                    lines.append(
                        f"| {x['input_len']} | {x['output_len']} | "
                        f"{x.get('request_throughput', 0):.2f} | "
                        f"{x.get('total_token_throughput', 0):.2f} | "
                        f"{x.get('output_token_throughput', 0):.2f} | "
                        f"{x.get('kv_cache_usage_pct', 'N/A')} | "
                        f"{x.get('prefix_cache_hit_rate_pct', 'N/A')} |"
                    )
        lines.append("")

    (run_group / "suite_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(suite_data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
