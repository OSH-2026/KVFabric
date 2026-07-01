#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


POLICIES = ("lru", "shared_aware", "family_protect")
SEGMENTS = ("low_guard", "high_main", "red_burst")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an acceptance-focused report for a long KVFabric run."
    )
    parser.add_argument("--run-root", required=True)
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


def collect_policy(run_root: Path, policy: str) -> dict[str, Any]:
    policy_dir = run_root / policy
    online_dir = policy_dir / "online_trace"
    if not online_dir.exists():
        online_dir = policy_dir / "online_duration"
    metrics = load_json(online_dir / "metrics.json")
    source = "final"
    if metrics is None:
        metrics = latest_jsonl(online_dir / "rolling_metrics.jsonl")
        source = "rolling" if metrics else "missing"
    lifecycle = load_json(policy_dir / "kvfabric_lifecycle_metrics.json")
    return {
        "policy": policy,
        "online_dir": online_dir,
        "metrics": metrics,
        "lifecycle": lifecycle,
        "source": source,
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


def value(metrics: dict[str, Any] | None, key: str) -> float | None:
    if not metrics:
        return None
    item = metrics.get(key)
    return float(item) if isinstance(item, int | float) else None


def ratio(value_: float | None, baseline: float | None) -> float | None:
    if value_ is None or baseline in (None, 0):
        return None
    return value_ / baseline


def pct_delta(value_: float | None, baseline: float | None) -> str:
    r = ratio(value_, baseline)
    return "n/a" if r is None else f"{(r - 1.0) * 100:+.2f}%"


def selected_slo_probe_label(policies: list[dict[str, Any]]) -> str | None:
    lru_metrics = policies[0]["metrics"] or {}
    lru_probes = lru_metrics.get("slo_probe_metrics") or {}
    best_label: str | None = None
    best_delta: float | None = None
    for item in policies[1:]:
        metrics = item["metrics"] or {}
        probes = metrics.get("slo_probe_metrics") or {}
        for label, probe in probes.items():
            lru_probe = lru_probes.get(label) or {}
            baseline = lru_probe.get("goodput_total_tokens_per_second")
            current = probe.get("goodput_total_tokens_per_second")
            if baseline in (None, 0) or current is None:
                continue
            delta = (float(current) - float(baseline)) / float(baseline)
            if best_delta is None or delta > best_delta:
                best_delta = delta
                best_label = label
    return best_label


def selected_goodput(metrics: dict[str, Any], probe_label: str | None) -> float | None:
    if probe_label:
        probe = (metrics.get("slo_probe_metrics") or {}).get(probe_label)
        if probe and probe.get("goodput_total_tokens_per_second") is not None:
            return probe.get("goodput_total_tokens_per_second")
    return value(metrics, "goodput_total_tokens_per_second")


def selected_segment_goodput(
    metrics: dict[str, Any] | None, segment_name: str, probe_label: str | None
) -> float | None:
    if not metrics:
        return None
    if probe_label:
        probe_segment = (
            ((metrics.get("slo_probe_metrics") or {}).get(probe_label) or {})
            .get("segment_metrics") or {}
        ).get(segment_name)
        if probe_segment and probe_segment.get("goodput_total_tokens_per_second") is not None:
            return float(probe_segment.get("goodput_total_tokens_per_second"))
    seg = segment(metrics, segment_name) or {}
    return value(seg, "goodput_total_tokens_per_second")


def number(value_: Any, digits: int = 2) -> str:
    if value_ is None:
        return "n/a"
    if isinstance(value_, int):
        return f"{value_:,}"
    if isinstance(value_, float):
        return f"{value_:,.{digits}f}"
    return str(value_)


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(":--" if i == 0 else "--:" for i in range(len(headers))) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def segment(metrics: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if not metrics:
        return None
    return (metrics.get("segment_metrics") or {}).get(name)


def discover_segments(policies: list[dict[str, Any]]) -> list[str]:
    existing = {
        name
        for item in policies
        for name in ((item["metrics"] or {}).get("segment_metrics") or {})
    }
    ordered = [name for name in SEGMENTS if name in existing]
    ordered.extend(sorted(existing - set(ordered)))
    return ordered


def low_guard_pass(
    metrics: dict[str, Any],
    lru: dict[str, Any],
    current_goodput: float | None = None,
    baseline_goodput: float | None = None,
) -> str:
    goodput = (
        current_goodput
        if current_goodput is not None
        else value(metrics, "goodput_total_tokens_per_second")
    )
    lru_goodput = (
        baseline_goodput
        if baseline_goodput is not None
        else value(lru, "goodput_total_tokens_per_second")
    )
    checks = [
        ratio(value(metrics, "latency_avg_seconds"), value(lru, "latency_avg_seconds")) is not None
        and ratio(value(metrics, "latency_avg_seconds"), value(lru, "latency_avg_seconds")) <= 1.03,
        ratio(value(metrics, "latency_p95_seconds"), value(lru, "latency_p95_seconds")) is not None
        and ratio(value(metrics, "latency_p95_seconds"), value(lru, "latency_p95_seconds")) <= 1.05,
        ratio(goodput, lru_goodput) is not None
        and ratio(goodput, lru_goodput) >= 0.97,
        ratio(value(metrics, "requests_per_second"), value(lru, "requests_per_second")) is not None
        and ratio(value(metrics, "requests_per_second"), value(lru, "requests_per_second")) >= 0.97,
        int(metrics.get("errors", 0)) == 0,
    ]
    return "pass" if all(checks) else "fail"


def class_share(metrics: dict[str, Any]) -> dict[str, float]:
    classes = metrics.get("class_metrics") or {}
    total = sum(float(item.get("completed", 0)) for item in classes.values())
    if total <= 0:
        return {}
    return {
        name: float(item.get("completed", 0)) / total
        for name, item in classes.items()
    }


def max_mix_drift(metrics: dict[str, Any], lru: dict[str, Any]) -> float:
    current = class_share(metrics)
    baseline = class_share(lru)
    names = set(current) | set(baseline)
    if not names:
        return 0.0
    return max(abs(current.get(name, 0.0) - baseline.get(name, 0.0)) for name in names)


def build_report(run_root: Path) -> str:
    policies = [collect_policy(run_root, policy) for policy in discover_policies(run_root)]
    lru_metrics = policies[0]["metrics"] or {}
    selected_probe_label = selected_slo_probe_label(policies)
    lru_selected_goodput = selected_goodput(lru_metrics, selected_probe_label)
    lines = [
        "# KVFabric Acceptance Run Analysis",
        "",
        f"Run root: `{run_root}`",
        "",
    ]

    completed = [item for item in policies if item["metrics"]]
    if len(completed) < len(policies):
        lines.extend(
            [
                "> Run is still in progress. Rolling metrics are used where final metrics are missing.",
                "",
            ]
        )

    rows = []
    for item in policies:
        metrics = item["metrics"]
        if not metrics:
            rows.append([item["policy"], "pending", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                item["source"],
                number(metrics.get("completed") or metrics.get("requests"), 0),
                number(metrics.get("errors"), 0),
                number(selected_goodput(metrics, selected_probe_label), 2),
                pct_delta(
                    selected_goodput(metrics, selected_probe_label),
                    lru_selected_goodput,
                ),
                f"{max_mix_drift(metrics, lru_metrics) * 100:.2f} pp"
                if item["policy"] != "lru"
                else "0.00 pp",
            ]
        )
    lines.extend(["## Overall", ""])
    lines.extend(
        table(
            [
                "Policy",
                "Source",
                "Completed",
                "Errors",
                "Goodput tok/s",
                "Goodput vs LRU",
                "Max class drift",
            ],
            rows,
        )
    )

    for segment_name in discover_segments(policies):
        lru_segment = segment(lru_metrics, segment_name) or {}
        lru_segment_goodput = selected_segment_goodput(
            lru_metrics, segment_name, selected_probe_label
        )
        rows = []
        for item in policies:
            seg = segment(item["metrics"], segment_name)
            if not seg:
                rows.append([item["policy"], "pending", "", "", "", "", "", ""])
                continue
            current_segment_goodput = selected_segment_goodput(
                item["metrics"], segment_name, selected_probe_label
            )
            verdict = ""
            if segment_name == "low_guard" and item["policy"] != "lru":
                verdict = low_guard_pass(
                    seg,
                    lru_segment,
                    current_segment_goodput,
                    lru_segment_goodput,
                )
            rows.append(
                [
                    item["policy"],
                    number(seg.get("completed"), 0),
                    number(seg.get("errors"), 0),
                    number(seg.get("requests_per_second"), 4),
                    number(current_segment_goodput, 2),
                    pct_delta(current_segment_goodput, lru_segment_goodput),
                    number(seg.get("latency_p95_seconds"), 3),
                    verdict,
                ]
            )
        lines.extend(["", f"## Segment: {segment_name}", ""])
        lines.extend(
            table(
                [
                    "Policy",
                    "Completed",
                    "Errors",
                    "Req/s",
                    "Goodput tok/s",
                    "Goodput vs LRU",
                    "P95 latency s",
                    "Verdict",
                ],
                rows,
            )
        )

    rows = []
    lru_lifecycle = policies[0]["lifecycle"] or {}
    for item in policies:
        lifecycle = item["lifecycle"]
        if not lifecycle:
            rows.append([item["policy"], "pending", "", "", "", "", "", "", "", "", "", ""])
            continue
        rows.append(
            [
                item["policy"],
                number(lifecycle.get("prefix_hit_tokens"), 0),
                f"{float(lifecycle.get('prefix_hit_rate', 0.0)) * 100:.2f}%",
                number(lifecycle.get("rebuilt_from_eviction_blocks"), 0),
                pct_delta(
                    value(lifecycle, "rebuilt_from_eviction_blocks"),
                    value(lru_lifecycle, "rebuilt_from_eviction_blocks"),
                ),
                number(lifecycle.get("cache_admission_saved_blocks"), 0),
                number(lifecycle.get("request_promoted_events"), 0),
                number(lifecycle.get("request_latency_promoted_events"), 0),
                number(lifecycle.get("request_defer_skipped_events"), 0),
                number(lifecycle.get("request_promotion_skipped_events"), 0),
                number(lifecycle.get("scheduler_promote_estimated_hit_tokens"), 0),
                number(lifecycle.get("scheduler_promote_avg_estimated_hit_tokens"), 1),
            ]
        )
    lines.extend(["", "## KV Cache Evidence", ""])
    lines.extend(
        table(
            [
                "Policy",
                "Prefix hit tokens",
                "Prefix hit rate",
                "Rebuilt blocks",
                "Rebuilt vs LRU",
                "Admission saved blocks",
                "Scheduler promotes",
                "Latency promotes",
                "Defer skips",
                "Promotion skips",
                "Promote hit tokens",
                "Promote avg hit tokens",
            ],
            rows,
        )
    )

    high_main = [
        item for item in policies
        if segment(item["metrics"], "high_main")
    ]
    if high_main:
        best = max(
            high_main,
            key=lambda item: selected_segment_goodput(
                item["metrics"], "high_main", selected_probe_label
            ) or 0.0,
        )
        lines.extend(
            [
                "",
                "## Takeaways",
                "",
                (
                    f"- Best high_main goodput policy: `{best['policy']}` "
                    f"({number(selected_segment_goodput(best['metrics'], 'high_main', selected_probe_label), 2)} tok/s, "
                    f"{pct_delta(selected_segment_goodput(best['metrics'], 'high_main', selected_probe_label), selected_segment_goodput(lru_metrics, 'high_main', selected_probe_label))} vs LRU)."
                ),
                "- If max class drift is above 3 percentage points, include a fixed-work check before making a strong throughput claim.",
            ]
        )
    if selected_probe_label:
        if not high_main:
            lines.extend(["", "## Takeaways", ""])
        lines.append(f"- Selected SLO probe: {selected_probe_label}.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    run_root = Path(args.run_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else (
        run_root / "acceptance_analysis.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(run_root), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
