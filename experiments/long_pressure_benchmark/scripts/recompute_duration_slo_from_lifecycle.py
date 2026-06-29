#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute server-side SLO goodput probes from KVFabric "
            "request_finished lifecycle events."
        )
    )
    parser.add_argument("--input", required=True, help="Lifecycle JSONL path or -.")
    parser.add_argument(
        "--thresholds",
        default="18,20,22,25,30,35",
        help="Comma-separated default SLO thresholds in seconds.",
    )
    parser.add_argument(
        "--class-slo",
        action="append",
        default=[],
        metavar="CLASS=SECONDS",
        help="Class-specific SLO override, repeatable.",
    )
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * pct))
    return ordered[index]


def parse_class_slo(items: list[str]) -> dict[str, float]:
    output: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --class-slo value: {item!r}")
        name, value = item.split("=", 1)
        output[name.strip()] = float(value)
    return output


def iter_events(path: str):
    if path == "-":
        for line in sys.stdin:
            if line.strip():
                yield json.loads(line)
        return
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def new_bucket() -> dict[str, Any]:
    return {
        "completed": 0,
        "total_tokens": 0,
        "goodput_tokens": 0,
        "slo_pass": 0,
        "slo_miss": 0,
        "latencies": [],
    }


def record(
    bucket: dict[str, Any],
    latency: float,
    total_tokens: int,
    passed: bool,
) -> None:
    bucket["completed"] += 1
    bucket["total_tokens"] += total_tokens
    bucket["latencies"].append(latency)
    if passed:
        bucket["goodput_tokens"] += total_tokens
        bucket["slo_pass"] += 1
    else:
        bucket["slo_miss"] += 1


def summarize_bucket(bucket: dict[str, Any], elapsed: float) -> dict[str, Any]:
    completed = int(bucket["completed"])
    miss = int(bucket["slo_miss"])
    latencies = list(bucket["latencies"])
    return {
        "completed": completed,
        "total_tokens": int(bucket["total_tokens"]),
        "total_tokens_per_second": int(bucket["total_tokens"]) / elapsed,
        "goodput_tokens": int(bucket["goodput_tokens"]),
        "goodput_tokens_per_second": int(bucket["goodput_tokens"]) / elapsed,
        "slo_pass": int(bucket["slo_pass"]),
        "slo_miss": miss,
        "slo_miss_rate": miss / completed if completed else 0.0,
        "latency_avg_seconds": statistics.mean(latencies) if latencies else 0.0,
        "latency_p50_seconds": percentile(latencies, 0.50),
        "latency_p95_seconds": percentile(latencies, 0.95),
    }


def main() -> None:
    args = parse_args()
    thresholds = sorted(
        {float(value) for value in args.thresholds.split(",") if value.strip()}
    )
    class_slo = parse_class_slo(args.class_slo)

    events = []
    for event in iter_events(args.input):
        if event.get("event") != "request_finished":
            continue
        arrival = int(event.get("arrival_time_ns") or 0)
        finish = int(event.get("finish_time_ns") or 0)
        if arrival <= 0 or finish <= arrival:
            continue
        prompt_tokens = int(event.get("prompt_tokens") or 0)
        output_tokens = int(event.get("output_tokens") or 0)
        events.append(
            {
                "latency": (finish - arrival) / 1e9,
                "total_tokens": prompt_tokens + output_tokens,
                "request_class": str(
                    event.get("hint_request_class")
                    or event.get("request_class")
                    or "unknown"
                ),
                "segment": str(event.get("hint_phase") or "unknown"),
                "arrival": arrival,
                "finish": finish,
            }
        )

    if not events:
        raise SystemExit("No request_finished events with arrival/finish times found.")

    elapsed = max(
        (max(event["finish"] for event in events) - min(event["arrival"] for event in events))
        / 1e9,
        1e-9,
    )
    output: dict[str, Any] = {
        "events": len(events),
        "elapsed_seconds": elapsed,
        "thresholds": thresholds,
        "class_slo_seconds": class_slo,
        "probes": {},
    }

    for threshold in thresholds:
        label = f"{threshold:g}s"
        overall = new_bucket()
        by_segment: dict[str, dict[str, Any]] = defaultdict(new_bucket)
        by_class: dict[str, dict[str, Any]] = defaultdict(new_bucket)
        for event in events:
            effective_slo = class_slo.get(event["request_class"], threshold)
            passed = effective_slo <= 0 or event["latency"] <= effective_slo
            record(overall, event["latency"], event["total_tokens"], passed)
            record(
                by_segment[event["segment"]],
                event["latency"],
                event["total_tokens"],
                passed,
            )
            record(
                by_class[event["request_class"]],
                event["latency"],
                event["total_tokens"],
                passed,
            )
        output["probes"][label] = {
            **summarize_bucket(overall, elapsed),
            "segment_metrics": {
                name: summarize_bucket(bucket, elapsed)
                for name, bucket in sorted(by_segment.items())
            },
            "class_metrics": {
                name: summarize_bucket(bucket, elapsed)
                for name, bucket in sorted(by_class.items())
            },
        }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
