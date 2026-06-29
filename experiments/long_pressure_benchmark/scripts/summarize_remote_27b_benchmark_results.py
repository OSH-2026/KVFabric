#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


POLICIES = ("lru", "shared_aware", "family_protect")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize KVFabric long benchmark results."
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


def discover_policies(run_root: Path) -> list[str]:
    if not run_root.exists():
        return list(POLICIES)
    existing = {
        path.name
        for path in run_root.iterdir()
        if path.is_dir()
        and ((path / "online_trace").exists() or (path / "online_duration").exists())
    }
    if not existing:
        return list(POLICIES)
    ordered = [policy for policy in POLICIES if policy in existing]
    ordered.extend(sorted(existing - set(ordered)))
    return ordered


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(":--" if i == 0 else "--:" for i in range(len(headers))) + " |",
    ]
    output.extend("| " + " | ".join(row) + " |" for row in rows)
    return output


def build_summary(run_root: Path) -> str:
    policies = [collect_policy(run_root, policy) for policy in discover_policies(run_root)]
    lru_metrics = policies[0]["metrics"] or {}
    lru_lifecycle = policies[0]["lifecycle"] or {}

    lines: list[str] = [
        "# KVFabric Benchmark Summary",
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
                f"- Session request ratio: {percent(trace_summary.get('session_request_ratio'), 2)}",
                f"- Burst request ratio: {percent(trace_summary.get('burst_request_ratio'), 2)}",
                f"- Unique tenants: {number(trace_summary.get('unique_tenants'), 0)}",
                f"- Unique clients: {number(trace_summary.get('unique_clients'), 0)}",
                f"- Unique families: {number(trace_summary.get('unique_families'), 0)}",
                "",
            ]
        )
    controller_rows = []
    for item in policies:
        controller = (item["lifecycle"] or {}).get("controller") or {}
        if controller:
            controller_rows.append(
                [
                    item["policy"],
                    str(controller.get("profile", "unknown")),
                    number(controller.get("admission_strength"), 2),
                    number(controller.get("eviction_strength"), 2),
                    number(controller.get("scheduler_strength"), 2),
                    number(controller.get("slo_protection_strength"), 2),
                    number(controller.get("hint_trust"), 2),
                    number(controller.get("low_reuse_cache_fraction"), 2),
                    number(controller.get("transient_cache_fraction"), 2),
                    number(controller.get("bypass_cache_fraction"), 2),
                    number(controller.get("durable_cache_fraction"), 2),
                ]
            )
    if controller_rows:
        lines.extend(["## Controller Parameters", ""])
        lines.extend(
            table(
                [
                    "Policy",
                    "Profile",
                    "Admission",
                    "Eviction",
                    "Scheduler",
                    "SLO protect",
                    "Hint trust",
                    "Low reuse frac",
                    "Transient frac",
                    "Bypass frac",
                    "Durable frac",
                ],
                controller_rows,
            )
        )
        lines.append("")

    rows = []
    for item in policies:
        metrics = item["metrics"]
        if not metrics:
            rows.append([item["policy"], "pending", "", "", "", "", "", "", "", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                number(metrics.get("requests") or metrics.get("completed"), 0),
                number(metrics.get("errors"), 0),
                number(metrics.get("offered_requests_per_second"), 4),
                number(metrics.get("requests_per_second"), 4),
                number(metrics.get("goodput_total_tokens_per_second"), 2),
                number(metrics.get("e2e_goodput_total_tokens_per_second"), 2),
                number(metrics.get("total_tokens_per_second"), 2),
                pct_delta(
                    metrics.get("goodput_total_tokens_per_second")
                    or metrics.get("total_tokens_per_second"),
                    lru_metrics.get("goodput_total_tokens_per_second")
                    or lru_metrics.get("total_tokens_per_second"),
                ),
                pct_delta(
                    metrics.get("e2e_goodput_total_tokens_per_second"),
                    lru_metrics.get("e2e_goodput_total_tokens_per_second"),
                ),
                number(metrics.get("latency_avg_seconds"), 3),
                number(metrics.get("latency_p95_seconds"), 3),
                number(metrics.get("e2e_latency_p95_seconds"), 3),
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
                "E2E goodput tok/s",
                "Total tok/s",
                "Goodput vs LRU",
                "E2E goodput vs LRU",
                "Avg latency s",
                "P95 latency s",
                "E2E P95 latency s",
                "Source",
            ],
            rows,
        )
    )
    error_rows = []
    for item in policies:
        metrics = item["metrics"] or {}
        error_types = metrics.get("error_types") or metrics.get("full_run_error_types")
        if error_types:
            error_rows.append(
                [
                    item["policy"],
                    json.dumps(error_types, ensure_ascii=False, sort_keys=True),
                ]
            )
    if error_rows:
        lines.extend(["", "## Error Types", ""])
        lines.extend(table(["Policy", "Errors"], error_rows))

    probe_labels = sorted(
        {
            probe_label
            for item in policies
            for probe_label in (
                (item["metrics"] or {}).get("slo_probe_metrics") or {}
            )
        }
    )
    if probe_labels:
        lines.extend(["", "## SLO Probe Metrics", ""])
        for probe_label in probe_labels:
            rows = []
            lru_probe = (
                (policies[0]["metrics"] or {}).get("slo_probe_metrics") or {}
            ).get(probe_label, {})
            lru_segments = lru_probe.get("segment_metrics") or {}
            for item in policies:
                metrics = item["metrics"] or {}
                probe = (metrics.get("slo_probe_metrics") or {}).get(probe_label)
                if not probe:
                    rows.append([item["policy"], "pending", "", "", "", "", "", ""])
                    continue
                segments = probe.get("segment_metrics") or {}
                high_main = segments.get("high_main") or {}
                red_burst = segments.get("red_burst") or {}
                lru_high_main = lru_segments.get("high_main") or {}
                lru_red_burst = lru_segments.get("red_burst") or {}
                rows.append(
                    [
                        item["policy"],
                        number(probe.get("goodput_total_tokens_per_second"), 2),
                        pct_delta(
                            probe.get("goodput_total_tokens_per_second"),
                            lru_probe.get("goodput_total_tokens_per_second"),
                        ),
                        percent(probe.get("slo_miss_rate"), 2),
                        number(
                            high_main.get("goodput_total_tokens_per_second"), 2
                        ),
                        pct_delta(
                            high_main.get("goodput_total_tokens_per_second"),
                            lru_high_main.get("goodput_total_tokens_per_second"),
                        ),
                        number(
                            red_burst.get("goodput_total_tokens_per_second"), 2
                        ),
                        pct_delta(
                            red_burst.get("goodput_total_tokens_per_second"),
                            lru_red_burst.get("goodput_total_tokens_per_second"),
                        ),
                    ]
                )
            lines.extend([f"### {probe_label}", ""])
            lines.extend(
                table(
                    [
                        "Policy",
                        "Goodput tok/s",
                        "Goodput vs LRU",
                        "SLO miss",
                        "High-main goodput",
                        "High-main vs LRU",
                        "Red-burst goodput",
                        "Red-burst vs LRU",
                    ],
                    rows,
                )
            )
            lines.append("")

    lines.extend(["", "## Lifecycle", ""])
    rows = []
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", "", "", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                percent(lifecycle.get("prefix_hit_rate"), 2),
                percent(lifecycle.get("eligible_prefix_hit_rate"), 2),
                percent(lifecycle.get("warm_family_prefix_hit_rate"), 2),
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
                "Eligible hit",
                "Warm-family hit",
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
            rows.append([item["policy"], "pending", "", "", "", "", "", "", "", "", "", "", ""])
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
                number(lifecycle.get("request_defer_skipped_events"), 0),
                number(lifecycle.get("request_promoted_events"), 0),
                number(lifecycle.get("request_latency_promoted_events"), 0),
                number(lifecycle.get("request_promotion_skipped_events"), 0),
                number(lifecycle.get("scheduler_promote_estimated_hit_tokens"), 0),
                number(lifecycle.get("scheduler_promote_avg_estimated_hit_tokens"), 1),
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
                "Defer skips",
                "Scheduler promotes",
                "Latency promotes",
                "Promotion skips",
                "Promote hit tokens",
                "Promote avg hit tokens",
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
            rows.append([item["policy"], "pending", "", "", "", "", "", "", ""])
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
                json.dumps(
                    lifecycle.get("scheduler_defer_skipped_reasons") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    lifecycle.get("scheduler_promotion_skipped_reasons") or {},
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
                "Defer skip reasons",
                "Promotion skip reasons",
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
                    rows.append([item["policy"], "pending", "", "", "", "", "", "", ""])
                    continue
                rows.append(
                    [
                        item["policy"],
                        number(class_metrics.get("completed"), 0),
                        number(class_metrics.get("total_tokens_per_second"), 2),
                        number(
                            class_metrics.get("goodput_total_tokens_per_second"), 2
                        ),
                        number(
                            class_metrics.get("e2e_goodput_total_tokens_per_second"),
                            2,
                        ),
                        number(class_metrics.get("latency_avg_seconds"), 3),
                        number(class_metrics.get("latency_p95_seconds"), 3),
                        number(class_metrics.get("e2e_latency_p95_seconds"), 3),
                        number(class_metrics.get("errors"), 0),
                    ]
                )
            lines.extend([f"### {class_name}", ""])
            lines.extend(
                table(
                    [
                        "Policy",
                        "Completed",
                        "Total tok/s",
                        "Goodput tok/s",
                        "E2E goodput tok/s",
                        "Avg latency s",
                        "P95 latency s",
                        "E2E P95 latency s",
                        "Errors",
                    ],
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
