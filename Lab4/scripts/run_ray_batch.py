#!/usr/bin/env python3
import argparse
import csv
import json
import math
import statistics as st
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_endpoints(path: Path, policy: str) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    endpoints = data["endpoints"]
    if policy == "server_only":
        endpoints = [e for e in endpoints if e["id"] == "server_gpu"]
    elif policy == "local_only":
        endpoints = [e for e in endpoints if e["id"] == "local_tunnel"]
    if not endpoints:
        raise ValueError(f"no endpoint matches policy={policy}")
    return endpoints


def parse_weights(value: str) -> dict[str, int]:
    weights: dict[str, int] = {}
    if not value:
        return weights
    for item in value.split(","):
        if not item.strip():
            continue
        name, raw_weight = item.split("=", 1)
        weights[name.strip()] = max(1, int(raw_weight))
    return weights


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[idx]


def call_completion(prompt: dict[str, Any], endpoint: dict[str, str], timeout: int, temperature: float) -> dict[str, Any]:
    base_url = endpoint["base_url"].rstrip("/")
    payload = {
        "prompt": prompt["prompt"],
        "n_predict": int(prompt.get("max_tokens") or 128),
        "temperature": temperature,
        "stream": False,
    }
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    status_code = None
    error = ""
    content = ""
    timings = {}
    try:
        resp = requests.post(f"{base_url}/completion", json=payload, timeout=timeout)
        status_code = resp.status_code
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        timings = data.get("timings", {}) or {}
    except Exception as exc:  # noqa: BLE001 - this is an experiment logger
        error = str(exc)
    ended_at = datetime.now(timezone.utc).isoformat()
    latency_s = time.perf_counter() - t0
    return {
        "id": prompt["id"],
        "category": prompt.get("category", ""),
        "endpoint_id": endpoint["id"],
        "endpoint_url": base_url,
        "started_at": started_at,
        "ended_at": ended_at,
        "latency_s": latency_s,
        "status_code": status_code,
        "success": bool(status_code and 200 <= status_code < 300 and not error),
        "error": error,
        "output_chars": len(content),
        "timings": timings,
    }


def choose_endpoint(endpoints: list[dict[str, str]], index: int) -> dict[str, str]:
    return endpoints[index % len(endpoints)]


def weighted_ring(endpoints: list[dict[str, str]], weights: dict[str, int]) -> list[dict[str, str]]:
    ring = []
    for endpoint in endpoints:
        weight = weights.get(endpoint["id"], int(endpoint.get("weight", 1)))
        ring.extend([endpoint] * max(1, weight))
    return ring or endpoints


def init_endpoint_state(endpoints: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    return {
        endpoint["id"]: {
            "ema_latency_s": math.nan,
            "success": 0,
            "failure": 0,
            "inflight": 0,
            "assigned": 0,
        }
        for endpoint in endpoints
    }


def choose_latency_aware(endpoints: list[dict[str, str]], state: dict[str, dict[str, float]]) -> dict[str, str]:
    def score(endpoint: dict[str, str]) -> tuple[float, int]:
        item = state[endpoint["id"]]
        ema = item["ema_latency_s"]
        if math.isnan(ema):
            ema = float(endpoint.get("initial_latency_s", 1.0))
        penalty = 1.0 + item["inflight"]
        if item["failure"] > item["success"]:
            penalty += 2.0
        return ema * penalty, int(item["assigned"])

    return min(endpoints, key=score)


def update_latency_state(row: dict[str, Any], state: dict[str, dict[str, float]], alpha: float = 0.35) -> None:
    item = state[row["endpoint_id"]]
    item["inflight"] = max(0, item["inflight"] - 1)
    item["assigned"] += 1
    if row.get("success"):
        item["success"] += 1
        latency = float(row["latency_s"])
        if math.isnan(item["ema_latency_s"]):
            item["ema_latency_s"] = latency
        else:
            item["ema_latency_s"] = alpha * latency + (1 - alpha) * item["ema_latency_s"]
    else:
        item["failure"] += 1
        if math.isnan(item["ema_latency_s"]):
            item["ema_latency_s"] = float(row.get("latency_s") or 30.0)
        else:
            item["ema_latency_s"] *= 1.5


def run_serial(prompts: list[dict[str, Any]], endpoints: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = []
    weights = parse_weights(args.endpoint_weights)
    ring = weighted_ring(endpoints, weights)
    state = init_endpoint_state(endpoints)
    for i, prompt in enumerate(prompts):
        if args.endpoint_policy == "weighted_static":
            endpoint = choose_endpoint(ring, i)
        elif args.endpoint_policy == "latency_aware":
            endpoint = choose_latency_aware(endpoints, state)
            state[endpoint["id"]]["inflight"] += 1
        else:
            endpoint = choose_endpoint(endpoints, i)
        row = call_completion(prompt, endpoint, args.timeout, args.temperature)
        if args.endpoint_policy == "latency_aware":
            update_latency_state(row, state)
        print(f"{row['id']} {row['endpoint_id']} success={row['success']} latency={row['latency_s']:.2f}s")
        rows.append(row)
    return rows


def run_ray(prompts: list[dict[str, Any]], endpoints: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, Any]]:
    import ray

    ray.init(ignore_reinit_error=True, include_dashboard=False, log_to_driver=False)

    @ray.remote
    def remote_call(prompt: dict[str, Any], endpoint: dict[str, str], timeout: int, temperature: float) -> dict[str, Any]:
        return call_completion(prompt, endpoint, timeout, temperature)

    rows = []
    pending = []
    pending_meta = {}
    next_index = 0
    weights = parse_weights(args.endpoint_weights)
    ring = weighted_ring(endpoints, weights)
    state = init_endpoint_state(endpoints)
    while next_index < len(prompts) or pending:
        while next_index < len(prompts) and len(pending) < args.concurrency:
            if args.endpoint_policy == "weighted_static":
                endpoint = choose_endpoint(ring, next_index)
            elif args.endpoint_policy == "latency_aware":
                endpoint = choose_latency_aware(endpoints, state)
                state[endpoint["id"]]["inflight"] += 1
            else:
                endpoint = choose_endpoint(endpoints, next_index)
            ref = remote_call.remote(prompts[next_index], endpoint, args.timeout, args.temperature)
            pending.append(ref)
            pending_meta[ref.hex()] = endpoint["id"]
            next_index += 1
        done, pending = ray.wait(pending, num_returns=1)
        row = ray.get(done[0])
        pending_meta.pop(done[0].hex(), None)
        if args.endpoint_policy == "latency_aware":
            update_latency_state(row, state)
        print(f"{row['id']} {row['endpoint_id']} success={row['success']} latency={row['latency_s']:.2f}s")
        rows.append(row)
    ray.shutdown()
    return rows


def write_rows(rows: list[dict[str, Any]], out_jsonl: Path) -> None:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(rows: list[dict[str, Any]], args: argparse.Namespace, total_elapsed_s: float) -> None:
    latencies = [float(r["latency_s"]) for r in rows if r.get("success")]
    out = Path(args.out_summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "label",
        "mode",
        "endpoint_policy",
        "concurrency",
        "requests",
        "success",
        "total_elapsed_s",
        "avg_latency_s",
        "p50_latency_s",
        "p95_latency_s",
        "avg_output_chars",
        "endpoint_counts",
        "endpoint_avg_latency_s",
    ]
    endpoint_counts = {}
    endpoint_latencies = {}
    for r in rows:
        endpoint_id = r["endpoint_id"]
        endpoint_counts[endpoint_id] = endpoint_counts.get(endpoint_id, 0) + 1
        if r.get("success"):
            endpoint_latencies.setdefault(endpoint_id, []).append(float(r["latency_s"]))
    endpoint_avg_latency = {
        endpoint_id: round(st.mean(values), 3) if values else 0
        for endpoint_id, values in endpoint_latencies.items()
    }
    row = {
        "label": args.label,
        "mode": args.mode,
        "endpoint_policy": args.endpoint_policy,
        "concurrency": args.concurrency,
        "requests": len(rows),
        "success": sum(1 for r in rows if r.get("success")),
        "total_elapsed_s": f"{total_elapsed_s:.3f}",
        "avg_latency_s": f"{(st.mean(latencies) if latencies else 0):.3f}",
        "p50_latency_s": f"{percentile(latencies, 0.50):.3f}",
        "p95_latency_s": f"{percentile(latencies, 0.95):.3f}",
        "avg_output_chars": f"{(st.mean([r['output_chars'] for r in rows]) if rows else 0):.1f}",
        "endpoint_counts": json.dumps(endpoint_counts, ensure_ascii=False, sort_keys=True),
        "endpoint_avg_latency_s": json.dumps(endpoint_avg_latency, ensure_ascii=False, sort_keys=True),
    }
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    print(json.dumps(row, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--endpoints", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--mode", choices=["serial", "ray"], required=True)
    parser.add_argument(
        "--endpoint-policy",
        choices=["round_robin", "server_only", "local_only", "weighted_static", "latency_aware"],
        default="round_robin",
    )
    parser.add_argument("--endpoint-weights", default="server_gpu=7,local_tunnel=1")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--temperature", type=float, default=0.2)
    args = parser.parse_args()

    prompts = read_jsonl(Path(args.prompts))
    if args.limit:
        prompts = prompts[: args.limit]
    endpoints = load_endpoints(Path(args.endpoints), args.endpoint_policy)

    t0 = time.perf_counter()
    if args.mode == "serial":
        rows = run_serial(prompts, endpoints, args)
    else:
        rows = run_ray(prompts, endpoints, args)
    total_elapsed_s = time.perf_counter() - t0
    write_rows(rows, Path(args.out_jsonl))
    write_summary(rows, args, total_elapsed_s)


if __name__ == "__main__":
    main()
