#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


POLICIES = ("lru", "shared_aware", "family_protect")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize remote 27B long benchmark results."
    )
    parser.add_argument("--run-root", required=True, help="Local run root.")
    parser.add_argument("--output", help="Markdown output path.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    return json.loads(last) if last else None


def pct_delta(value: float | None, baseline: float | None) -> str:
    if value is None or baseline in (None, 0):
        return "n/a"
    return f"{((value - baseline) / baseline) * 100:+.2f}%"


def number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def percent(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"


def collect_policy(run_root: Path, policy: str) -> dict[str, Any]:
    policy_dir = run_root / policy
    online_dir = policy_dir / "online_trace"
    if not online_dir.exists():
        online_dir = policy_dir / "online_duration"
    metrics = load_json(online_dir / "metrics.json")
    metric_source = "final"
    if metrics is None:
        metrics = latest_jsonl(online_dir / "rolling_metrics.jsonl")
        metric_source = "rolling" if metrics is not None else "missing"
    lifecycle = load_json(policy_dir / "kvfabric_lifecycle_metrics.json")
    prometheus = load_json(policy_dir / "prometheus_metrics_summary.json")
    class_metrics = load_json(online_dir / "class_metrics.json")
    if metrics and class_metrics and "class_metrics" not in metrics:
        metrics["class_metrics"] = class_metrics
    trace_summary = load_json(online_dir / "trace_summary.json")
    return {
        "policy": policy,
        "metrics": metrics,
        "metric_source": metric_source,
        "lifecycle": lifecycle,
        "prometheus": prometheus,
        "trace_summary": trace_summary,
    }


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(":--" if i == 0 else "--:" for i in range(len(headers))) + " |",
    ]
    output.extend("| " + " | ".join(row) + " |" for row in rows)
    return output


def build_summary(run_root: Path) -> str:
    policies = [collect_policy(run_root, policy) for policy in POLICIES]
    lru_metrics = policies[0]["metrics"] or {}
    lru_lifecycle = policies[0]["lifecycle"] or {}

    lines: list[str] = [
        "# Remote qwen3_5_27b Benchmark Summary",
        "",
        f"Run root: `{run_root}`",
        "",
        "## Throughput And Latency",
        "",
    ]
    trace_summary = next(
        (item["trace_summary"] for item in policies if item.get("trace_summary")),
        None,
    )
    if trace_summary:
        settings = trace_summary.get("settings") or {}
        lines.extend(
            [
                "## Trace",
                "",
                f"- Profile: `{settings.get('profile', 'unknown')}`",
                f"- Trace SHA256: `{trace_summary.get('trace_sha256', 'unknown')}`",
                f"- Requests: {number(trace_summary.get('requests'), 0)}",
                f"- Duration seconds: {number(trace_summary.get('duration_seconds'), 1)}",
                f"- Target request rate: {number(trace_summary.get('request_rate'), 4)}",
                f"- Actual request rate: {number(trace_summary.get('actual_request_rate'), 4)}",
                f"- Hint regime: `{settings.get('hint_regime', 'unknown')}`",
                "",
            ]
        )

    rows = []
    for item in policies:
        metrics = item["metrics"]
        if not metrics:
            rows.append([item["policy"], "pending", "", "", "", "", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                number(metrics.get("requests") or metrics.get("completed"), 0),
                number(metrics.get("errors"), 0),
                number(metrics.get("offered_requests_per_second"), 4),
                number(metrics.get("requests_per_second"), 4),
                number(metrics.get("goodput_total_tokens_per_second"), 2),
                number(metrics.get("total_tokens_per_second"), 2),
                pct_delta(
                    metrics.get("goodput_total_tokens_per_second")
                    or metrics.get("total_tokens_per_second"),
                    lru_metrics.get("goodput_total_tokens_per_second")
                    or lru_metrics.get("total_tokens_per_second"),
                ),
                number(metrics.get("latency_avg_seconds"), 3),
                number(metrics.get("latency_p95_seconds"), 3),
                item["metric_source"],
            ]
        )
    lines.extend(
        table(
            [
                "Policy",
                "Requests",
                "Errors",
                "Offered req/s",
                "Req/s",
                "Goodput tok/s",
                "Total tok/s",
                "Goodput vs LRU",
                "Avg latency s",
                "P95 latency s",
                "Source",
            ],
            rows,
        )
    )

    lines.extend(["", "## Lifecycle", ""])
    rows = []
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                percent(lifecycle.get("prefix_hit_rate"), 2),
                number(lifecycle.get("prefix_hit_tokens"), 0),
                number(lifecycle.get("evicted_blocks"), 0),
                number(lifecycle.get("rebuilt_from_eviction_blocks"), 0),
                percent(lifecycle.get("regretful_eviction_proxy_rate"), 4),
                pct_delta(
                    lifecycle.get("rebuilt_from_eviction_blocks"),
                    lru_lifecycle.get("rebuilt_from_eviction_blocks"),
                ),
            ]
        )
    lines.extend(
        table(
            [
                "Policy",
                "Prefix hit",
                "Prefix hit tokens",
                "Evicted",
                "Rebuilt",
                "Regret proxy",
                "Rebuilt vs LRU",
            ],
            rows,
        )
    )

    lines.extend(["", "## Admission And Scheduler", ""])
    rows = []
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", "", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                number(lifecycle.get("cache_admission_limited_events"), 0),
                number(lifecycle.get("cache_admission_saved_blocks"), 0),
                percent(lifecycle.get("cache_admission_saved_ratio"), 2),
                percent(
                    lifecycle.get("cache_admission_avg_eviction_risk_ratio"), 2
                ),
                number(lifecycle.get("request_deferred_events"), 0),
                number(lifecycle.get("request_promoted_events"), 0),
                percent(
                    lifecycle.get("scheduler_defer_avg_eviction_risk_ratio"), 2
                ),
            ]
        )
    lines.extend(
        table(
            [
                "Policy",
                "Admission limited",
                "Saved blocks",
                "Saved ratio",
                "Admission risk avg",
                "Scheduler defers",
                "Scheduler promotes",
                "Defer risk avg",
            ],
            rows,
        )
    )

    lines.extend(["", "## Hint-Aware Behavior", ""])
    rows = []
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                number(lifecycle.get("request_hints_observed_events"), 0),
                percent(lifecycle.get("request_hint_coverage_vs_finished"), 2),
                number(lifecycle.get("hint_family_count"), 0),
                json.dumps(
                    lifecycle.get("request_hint_cache_priorities") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    lifecycle.get("request_hint_expected_reuse") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    lifecycle.get("scheduler_defer_reasons") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )
    lines.extend(
        table(
            [
                "Policy",
                "Hint events",
                "Coverage",
                "Hint families",
                "Priorities",
                "Expected reuse",
                "Defer reasons",
            ],
            rows,
        )
    )

    lines.extend(["", "## Admission Reasons", ""])
    rows = []
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", ""])
            continue
        rows.append(
            [
                item["policy"],
                json.dumps(
                    lifecycle.get("cache_admission_reasons") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    lifecycle.get("cache_admission_hint_classes") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )
    lines.extend(table(["Policy", "Admission reasons", "Limited hint classes"], rows))

    class_names = sorted(
        {
            class_name
            for item in policies
            for class_name in ((item["metrics"] or {}).get("class_metrics") or {})
        }
    )
    if class_names:
        lines.extend(["", "## Request Class Metrics", ""])
        for class_name in class_names:
            rows = []
            for item in policies:
                metrics = item["metrics"] or {}
                class_metrics = (metrics.get("class_metrics") or {}).get(class_name)
                if not class_metrics:
                    rows.append([item["policy"], "pending", "", "", "", ""])
                    continue
                rows.append(
                    [
                        item["policy"],
                        number(class_metrics.get("completed"), 0),
                        number(class_metrics.get("total_tokens_per_second"), 2),
                        number(class_metrics.get("latency_avg_seconds"), 3),
                        number(class_metrics.get("latency_p95_seconds"), 3),
                        number(class_metrics.get("errors"), 0),
                    ]
                )
            lines.extend([f"### {class_name}", ""])
            lines.extend(
                table(
                    ["Policy", "Completed", "Total tok/s", "Avg latency s", "P95 latency s", "Errors"],
                    rows,
                )
            )
            lines.append("")

    segment_names = sorted(
        {
            segment_name
            for item in policies
            for segment_name in ((item["metrics"] or {}).get("segment_metrics") or {})
        }
    )
    if segment_names:
        lines.extend(["", "## Segment Metrics", ""])
        for segment_name in segment_names:
            rows = []
            lru_segment = (
                (policies[0]["metrics"] or {}).get("segment_metrics") or {}
            ).get(segment_name, {})
            for item in policies:
                metrics = item["metrics"] or {}
                segment_metrics = (metrics.get("segment_metrics") or {}).get(
                    segment_name
                )
                if not segment_metrics:
                    rows.append([item["policy"], "pending", "", "", "", "", ""])
                    continue
                goodput = segment_metrics.get("goodput_total_tokens_per_second")
                rows.append(
                    [
                        item["policy"],
                        number(segment_metrics.get("completed"), 0),
                        number(segment_metrics.get("requests_per_second"), 4),
                        number(goodput, 2),
                        pct_delta(
                            goodput,
                            lru_segment.get("goodput_total_tokens_per_second"),
                        ),
                        number(segment_metrics.get("latency_avg_seconds"), 3),
                        number(segment_metrics.get("latency_p95_seconds"), 3),
                    ]
                )
            lines.extend([f"### {segment_name}", ""])
            lines.extend(
                table(
                    [
                        "Policy",
                        "Completed",
                        "Req/s",
                        "Goodput tok/s",
                        "Goodput vs LRU",
                        "Avg latency s",
                        "P95 latency s",
                    ],
                    rows,
                )
            )
            lines.append("")

    lines.extend(["## Notes", ""])
    completed = [item for item in policies if item["metrics"] and item["lifecycle"]]
    if len(completed) < len(policies):
        lines.append("- Run is still in progress or some policy summaries are not yet available.")
    else:
        best = max(
            completed,
            key=lambda item: (
                item["metrics"].get("goodput_total_tokens_per_second")
                or item["metrics"].get("total_tokens_per_second", 0)
            ),
        )
        lines.append(
            f"- Best throughput policy: `{best['policy']}` "
            f"({number(best['metrics'].get('goodput_total_tokens_per_second') or best['metrics'].get('total_tokens_per_second'), 2)} goodput tok/s)."
        )
        for item in completed:
            if item["policy"] == "lru":
                continue
            lines.append(
                f"- `{item['policy']}` total tok/s delta vs LRU: "
                f"{pct_delta(item['metrics'].get('total_tokens_per_second'), lru_metrics.get('total_tokens_per_second'))}; "
                f"rebuilt delta vs LRU: "
                f"{pct_delta(item['lifecycle'].get('rebuilt_from_eviction_blocks'), lru_lifecycle.get('rebuilt_from_eviction_blocks'))}."
            )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    run_root = Path(args.run_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else (
        run_root / "remote_27b_benchmark_summary.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_summary(run_root), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
