from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a quality suite run group.")
    parser.add_argument("run_group_dir", help="Path to suite run directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_group_dir = Path(args.run_group_dir).expanduser().resolve()
    if not run_group_dir.is_dir():
        raise FileNotFoundError(f"Run group directory not found: {run_group_dir}")

    variant_dirs = sorted(
        [
            path
            for path in run_group_dir.iterdir()
            if path.is_dir() and (path / "metrics.json").exists()
        ]
    )
    if not variant_dirs:
        raise FileNotFoundError(f"No variant run directories found under: {run_group_dir}")

    variants = []
    for variant_dir in variant_dirs:
        metrics = json.loads((variant_dir / "metrics.json").read_text(encoding="utf-8"))
        variants.append(
            {
                "variant_name": metrics["variant_name"],
                "overall_avg_score": metrics["overall_avg_score"],
                "overall_pass_rate": metrics["overall_pass_rate"],
                "output_tokens_per_second": metrics["output_tokens_per_second"],
                "load_seconds": metrics["load_seconds"],
                "inference_seconds": metrics["inference_seconds"],
                "category_summary": metrics["category_summary"],
            }
        )

    baseline = variants[0]
    for variant in variants[1:]:
        variant["avg_score_delta_vs_baseline"] = (
            variant["overall_avg_score"] - baseline["overall_avg_score"]
        )
        variant["pass_rate_delta_vs_baseline"] = (
            variant["overall_pass_rate"] - baseline["overall_pass_rate"]
        )
        variant["output_tps_delta_vs_baseline"] = (
            variant["output_tokens_per_second"] - baseline["output_tokens_per_second"]
        )

    payload = {
        "run_group_dir": str(run_group_dir),
        "baseline_variant": baseline["variant_name"],
        "variants": variants,
    }

    (run_group_dir / "suite_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# {run_group_dir.name}",
        "",
        f"- Baseline variant: {baseline['variant_name']}",
        "",
        "## Variant Summary",
        "",
    ]

    for variant in variants:
        lines.append(
            f"- {variant['variant_name']}: avg_score={variant['overall_avg_score']:.3f}, pass_rate={variant['overall_pass_rate']:.3f}, output_tokens/s={variant['output_tokens_per_second']:.2f}"
        )
        if variant["variant_name"] != baseline["variant_name"]:
            lines.append(
                f"  delta_vs_baseline: avg_score={variant['avg_score_delta_vs_baseline']:+.3f}, pass_rate={variant['pass_rate_delta_vs_baseline']:+.3f}, output_tokens/s={variant['output_tps_delta_vs_baseline']:+.2f}"
            )

    lines.extend(["", "## Category Summary", ""])

    categories = sorted(
        {
            category
            for variant in variants
            for category in variant["category_summary"].keys()
        }
    )
    for category in categories:
        lines.append(f"- {category}")
        for variant in variants:
            summary = variant["category_summary"].get(category)
            if not summary:
                continue
            lines.append(
                f"  {variant['variant_name']}: avg_score={summary['avg_score']:.3f}, pass_rate={summary['pass_rate']:.3f}, items={summary['items']}"
            )

    (run_group_dir / "suite_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
