#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import random
import statistics
import time
from collections import Counter
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "online_trace_loadgen.py requires httpx. Install it in the vLLM env."
    ) from exc

from online_batch import percentile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a deterministic open-loop trace against vLLM."
    )
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", required=True)
    parser.add_argument("--hint-regime", default=None,
                        choices=("full_hints", "partial_hints", "noisy_hints",
                                 "no_hints"))
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--max-in-flight", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--metrics-interval", type=float, default=30.0)
    parser.add_argument("--raw-sample-rate", type=float, default=0.02)
    parser.add_argument("--raw-sample-limit", type=int, default=2000)
    parser.add_argument("--random-seed", type=int, default=20260624)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_trace(trace_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trace_path = trace_dir / "trace.jsonl"
    summary_path = trace_dir / "trace_summary.json"
    if not trace_path.exists():
        raise FileNotFoundError(trace_path)
    entries = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not entries:
        raise ValueError(f"Trace is empty: {trace_path}")
    summary = load_json(summary_path) if summary_path.exists() else {}
    return entries, summary


def read_prompt(trace_dir: Path, prompt_ref: str) -> list[dict[str, str]]:
    prompt_path = trace_dir / prompt_ref
    data = load_json(prompt_path)
    return data["messages"]


def derive_headers(
    entry: dict[str, Any],
    hint_regime: str,
    rng: random.Random,
) -> dict[str, str] | None:
    if hint_regime == "no_hints":
        return None

    request_class = str(entry.get("request_class", "unknown"))
    cache_priority = str(entry.get("cache_priority", "normal"))
    expected_reuse = str(entry.get("expected_reuse", "unknown"))

    if hint_regime == "noisy_hints" and rng.random() < 0.15:
        if expected_reuse == "durable":
            expected_reuse = "none"
            cache_priority = "low"
        elif expected_reuse == "none":
            expected_reuse = "durable"
            cache_priority = "high"
        else:
            expected_reuse = "unknown"
            cache_priority = "normal"

    headers = {
        "x-kvfabric-request-class": request_class,
        "x-kvfabric-burst": "true" if entry.get("burst") else "false",
    }
    tenant_id = entry.get("tenant_id")
    session_id = entry.get("session_id")
    family_id = entry.get("family_id")
    phase = entry.get("phase")

    if hint_regime in {"partial_hints", "full_hints", "noisy_hints"}:
        if tenant_id:
            headers["x-kvfabric-tenant-id"] = str(tenant_id)
        if session_id:
            headers["x-kvfabric-family-id"] = str(session_id)
        elif family_id and hint_regime != "partial_hints":
            headers["x-kvfabric-family-id"] = str(family_id)

    if hint_regime in {"full_hints", "noisy_hints"}:
        headers["x-kvfabric-cache-priority"] = cache_priority
        headers["x-kvfabric-expected-reuse"] = expected_reuse
        if phase:
            headers["x-kvfabric-phase"] = str(phase)
    elif hint_regime == "partial_hints":
        if phase and session_id:
            headers["x-kvfabric-phase"] = str(phase)

    return headers


class RunStats:
    def __init__(self, started: float, warmup_seconds: float) -> None:
        self.started = started
        self.warmup_seconds = warmup_seconds
        self.offered = 0
        self.completed = 0
        self.errors = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.latencies: list[float] = []
        self.send_delays: list[float] = []
        self.queue_delays: list[float] = []
        self.recent_latencies: deque[float] = deque(maxlen=4096)
        self.sampled_outputs = 0
        self.error_types: Counter[str] = Counter()
        self.class_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "offered": 0,
                "completed": 0,
                "errors": 0,
                "error_types": Counter(),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latencies": [],
                "send_delays": [],
                "recent_latencies": deque(maxlen=1024),
            }
        )
        self.measured = {
            "offered": 0,
            "completed": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latencies": [],
            "send_delays": [],
            "error_types": Counter(),
        }

    def record_offered(self, request_class: str, measured: bool) -> None:
        self.offered += 1
        self.class_stats[request_class]["offered"] += 1
        if measured:
            self.measured["offered"] += 1

    def record_success(
        self,
        request_class: str,
        usage: dict[str, Any],
        latency: float,
        send_delay: float,
        measured: bool,
    ) -> None:
        self.completed += 1
        self.latencies.append(latency)
        self.recent_latencies.append(latency)
        self.send_delays.append(send_delay)
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens

        stats = self.class_stats[request_class]
        stats["completed"] += 1
        stats["prompt_tokens"] += prompt_tokens
        stats["completion_tokens"] += completion_tokens
        stats["total_tokens"] += total_tokens
        stats["latencies"].append(latency)
        stats["send_delays"].append(send_delay)
        stats["recent_latencies"].append(latency)

        if measured:
            self.measured["completed"] += 1
            self.measured["prompt_tokens"] += prompt_tokens
            self.measured["completion_tokens"] += completion_tokens
            self.measured["total_tokens"] += total_tokens
            self.measured["latencies"].append(latency)
            self.measured["send_delays"].append(send_delay)

    def record_error(
        self,
        request_class: str,
        error_type: str,
        send_delay: float,
        measured: bool,
    ) -> None:
        self.errors += 1
        self.error_types[error_type] += 1
        self.class_stats[request_class]["errors"] += 1
        self.class_stats[request_class]["error_types"][error_type] += 1
        self.send_delays.append(send_delay)
        if measured:
            self.measured["errors"] += 1
            self.measured["error_types"][error_type] += 1
            self.measured["send_delays"].append(send_delay)

    def _base_snapshot(
        self,
        elapsed: float,
        completed: int,
        errors: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latencies: list[float],
        send_delays: list[float],
    ) -> dict[str, Any]:
        return {
            "completed": completed,
            "errors": errors,
            "requests_per_second": completed / elapsed if elapsed > 0 else 0.0,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_tokens_per_second": (
                prompt_tokens / elapsed if elapsed > 0 else 0.0
            ),
            "completion_tokens_per_second": (
                completion_tokens / elapsed if elapsed > 0 else 0.0
            ),
            "total_tokens_per_second": (
                total_tokens / elapsed if elapsed > 0 else 0.0
            ),
            "latency_avg_seconds": statistics.mean(latencies)
            if latencies
            else 0.0,
            "latency_p50_seconds": percentile(latencies, 0.50),
            "latency_p95_seconds": percentile(latencies, 0.95),
            "latency_p99_seconds": percentile(latencies, 0.99),
            "send_delay_avg_seconds": statistics.mean(send_delays)
            if send_delays
            else 0.0,
            "send_delay_p95_seconds": percentile(send_delays, 0.95),
        }

    def final_metrics(self, elapsed: float, measured_elapsed: float) -> dict[str, Any]:
        measured = self._base_snapshot(
            max(measured_elapsed, 1e-9),
            int(self.measured["completed"]),
            int(self.measured["errors"]),
            int(self.measured["prompt_tokens"]),
            int(self.measured["completion_tokens"]),
            int(self.measured["total_tokens"]),
            list(self.measured["latencies"]),
            list(self.measured["send_delays"]),
        )
        full = self._base_snapshot(
            max(elapsed, 1e-9),
            self.completed,
            self.errors,
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.latencies,
            self.send_delays,
        )
        class_metrics = {}
        for request_class, stats in sorted(self.class_stats.items()):
            class_metrics[request_class] = {
                **self._base_snapshot(
                    max(elapsed, 1e-9),
                    int(stats["completed"]),
                    int(stats["errors"]),
                    int(stats["prompt_tokens"]),
                    int(stats["completion_tokens"]),
                    int(stats["total_tokens"]),
                    list(stats["latencies"]),
                    list(stats["send_delays"]),
                ),
                "offered": int(stats["offered"]),
                "error_types": dict(sorted(stats["error_types"].items())),
            }
        return {
            **measured,
            "metric_window": "warmup_excluded",
            "warmup_seconds": self.warmup_seconds,
            "elapsed_seconds": elapsed,
            "measured_elapsed_seconds": measured_elapsed,
            "offered": self.offered,
            "measured_offered": int(self.measured["offered"]),
            "error_types": dict(sorted(self.measured["error_types"].items())),
            "full_run_error_types": dict(sorted(self.error_types.items())),
            "offered_requests_per_second": (
                self.offered / elapsed if elapsed > 0 else 0.0
            ),
            "measured_offered_requests_per_second": (
                int(self.measured["offered"]) / measured_elapsed
                if measured_elapsed > 0
                else 0.0
            ),
            "full_run_metrics": full,
            "class_metrics": class_metrics,
        }


async def post_chat(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None,
    timeout: float,
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    response = await client.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return time.perf_counter() - started, response.json()


def select_prometheus_lines(text: str) -> list[str]:
    needles = ("kv_cache", "prefix", "gpu_cache", "cache_config", "num_requests")
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(needle in lowered for needle in needles):
            lines.append(line)
    return lines


async def metrics_sampler(
    client: httpx.AsyncClient,
    metrics_url: str,
    stats: RunStats,
    stats_lock: asyncio.Lock,
    output_dir: Path,
    interval: float,
    stop_event: asyncio.Event,
) -> None:
    rolling_path = output_dir / "rolling_metrics.jsonl"
    prometheus_path = output_dir / "prometheus_cache_samples.jsonl"
    with rolling_path.open("w", encoding="utf-8") as rolling_file, (
        prometheus_path.open("w", encoding="utf-8")
    ) as prometheus_file:
        while not stop_event.is_set():
            await asyncio.sleep(interval)
            now = time.perf_counter()
            async with stats_lock:
                elapsed = max(now - stats.started, 1e-9)
                recent = list(stats.recent_latencies)
                snapshot = {
                    "elapsed_seconds": elapsed,
                    "offered": stats.offered,
                    "completed": stats.completed,
                    "errors": stats.errors,
                    "requests_per_second": stats.completed / elapsed,
                    "offered_requests_per_second": stats.offered / elapsed,
                    "total_tokens_per_second": stats.total_tokens / elapsed,
                    "latency_avg_seconds": statistics.mean(recent)
                    if recent
                    else 0.0,
                    "latency_p95_seconds": percentile(recent, 0.95),
                    "send_delay_p95_seconds": percentile(stats.send_delays, 0.95),
                }
            rolling_file.write(json.dumps(snapshot, sort_keys=True) + "\n")
            rolling_file.flush()
            try:
                response = await client.get(metrics_url, timeout=10.0)
                response.raise_for_status()
                prometheus_file.write(
                    json.dumps(
                        {
                            "elapsed_seconds": max(now - stats.started, 0.0),
                            "lines": select_prometheus_lines(response.text),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                prometheus_file.flush()
            except Exception as exc:  # noqa: BLE001
                prometheus_file.write(
                    json.dumps(
                        {
                            "elapsed_seconds": max(now - stats.started, 0.0),
                            "error": repr(exc),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                prometheus_file.flush()


async def replay(args: argparse.Namespace) -> dict[str, Any]:
    trace_dir = Path(args.trace_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    entries, trace_summary = load_trace(trace_dir)
    hint_regime = args.hint_regime or str(
        trace_summary.get("settings", {}).get("hint_regime", "partial_hints")
    )
    rng = random.Random(args.random_seed)
    sample_rng = random.Random(args.random_seed + 1)

    (output_dir / "trace_summary.json").write_text(
        json.dumps(trace_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "env.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "host": args.host,
                "port": args.port,
                "model": args.model,
                "trace_dir": str(trace_dir),
                "trace_sha256": trace_summary.get("trace_sha256"),
                "hint_regime": hint_regime,
                "warmup_seconds": args.warmup_seconds,
                "max_in_flight": args.max_in_flight,
                "requests": len(entries),
                "trace_duration_seconds": (
                    max(float(e["scheduled_at_seconds"]) for e in entries)
                    if entries
                    else 0.0
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    metrics_url = f"http://{args.host}:{args.port}/metrics"
    limits = httpx.Limits(
        max_connections=max(args.max_in_flight * 2, 16),
        max_keepalive_connections=max(args.max_in_flight, 8),
    )
    stats = RunStats(started=time.perf_counter(), warmup_seconds=args.warmup_seconds)
    stats_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.max_in_flight)
    stop_event = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []

    async with httpx.AsyncClient(limits=limits) as client:
        sampler = asyncio.create_task(
            metrics_sampler(
                client=client,
                metrics_url=metrics_url,
                stats=stats,
                stats_lock=stats_lock,
                output_dir=output_dir,
                interval=args.metrics_interval,
                stop_event=stop_event,
            )
        )
        with (output_dir / "raw_outputs_sample.jsonl").open(
            "w", encoding="utf-8"
        ) as raw_file:

            async def send_one(entry: dict[str, Any]) -> None:
                request_class = str(entry.get("request_class", "unknown"))
                scheduled_at = float(entry.get("scheduled_at_seconds", 0.0))
                due = stats.started + scheduled_at
                measured = scheduled_at >= args.warmup_seconds
                await semaphore.acquire()
                try:
                    send_started = time.perf_counter()
                    send_delay = max(send_started - due, 0.0)
                    async with stats_lock:
                        stats.record_offered(request_class, measured)
                    messages = read_prompt(trace_dir, str(entry["prompt_ref"]))
                    payload = {
                        "model": args.model,
                        "messages": messages,
                        "temperature": float(entry.get("temperature", 0.0)),
                        "max_tokens": int(entry.get("max_tokens", 128)),
                    }
                    headers = derive_headers(entry, hint_regime, rng)
                    try:
                        latency, data = await post_chat(
                            client,
                            url,
                            payload,
                            headers,
                            args.timeout,
                        )
                        usage = data.get("usage", {})
                        should_sample = (
                            args.raw_sample_rate >= 1.0
                            or sample_rng.random() < args.raw_sample_rate
                        )
                        async with stats_lock:
                            stats.record_success(
                                request_class,
                                usage,
                                latency,
                                send_delay,
                                measured,
                            )
                            if (
                                should_sample
                                and stats.sampled_outputs < args.raw_sample_limit
                            ):
                                choice = data.get("choices", [{}])[0]
                                message = choice.get("message", {})
                                raw_file.write(
                                    json.dumps(
                                        {
                                            "request_id": entry.get("request_id"),
                                            "scheduled_at_seconds": scheduled_at,
                                            "request_class": request_class,
                                            "session_id": entry.get("session_id"),
                                            "family_id": entry.get("family_id"),
                                            "turn_index": entry.get("turn_index"),
                                            "hint_regime": hint_regime,
                                            "headers": headers or {},
                                            "send_delay_seconds": send_delay,
                                            "latency_seconds": latency,
                                            "usage": usage,
                                            "output": message.get("content", ""),
                                        },
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                )
                                raw_file.flush()
                                stats.sampled_outputs += 1
                    except Exception as exc:  # noqa: BLE001
                        error_type = type(exc).__name__
                        async with stats_lock:
                            stats.record_error(
                                request_class,
                                error_type,
                                send_delay,
                                measured,
                            )
                            raw_file.write(
                                json.dumps(
                                    {
                                        "request_id": entry.get("request_id"),
                                        "scheduled_at_seconds": scheduled_at,
                                        "request_class": request_class,
                                        "hint_regime": hint_regime,
                                        "headers": headers or {},
                                        "send_delay_seconds": send_delay,
                                        "error_type": error_type,
                                        "error": repr(exc),
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                            raw_file.flush()
                finally:
                    semaphore.release()

            for entry in entries:
                scheduled_at = float(entry.get("scheduled_at_seconds", 0.0))
                await asyncio.sleep(max(stats.started + scheduled_at - time.perf_counter(), 0.0))
                tasks.append(asyncio.create_task(send_one(entry)))

            if tasks:
                await asyncio.gather(*tasks)

        stop_event.set()
        await sampler

    elapsed = max(time.perf_counter() - stats.started, 1e-9)
    trace_duration = max(float(e["scheduled_at_seconds"]) for e in entries)
    measured_elapsed = max(elapsed - args.warmup_seconds, 1e-9)
    async with stats_lock:
        metrics = stats.final_metrics(elapsed, measured_elapsed)
    metrics.update(
        {
            "trace_duration_seconds": trace_duration,
            "trace_sha256": trace_summary.get("trace_sha256"),
            "trace_profile": trace_summary.get("settings", {}).get("profile"),
            "hint_regime": hint_regime,
            "requests": metrics["completed"],
            "errors": metrics["errors"],
            "total_seconds": elapsed,
        }
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "class_metrics.json").write_text(
        json.dumps(metrics["class_metrics"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                f"# Trace replay: {metrics.get('trace_profile')}",
                "",
                f"- Trace SHA256: {metrics.get('trace_sha256')}",
                f"- Hint regime: {hint_regime}",
                f"- Warmup seconds: {args.warmup_seconds:.1f}",
                f"- Offered: {metrics['offered']}",
                f"- Completed: {metrics['completed']}",
                f"- Errors: {metrics['errors']}",
                f"- Measured offered req/s: {metrics['measured_offered_requests_per_second']:.4f}",
                f"- Measured completed req/s: {metrics['requests_per_second']:.4f}",
                f"- Measured total tok/s: {metrics['total_tokens_per_second']:.2f}",
                f"- Latency avg seconds: {metrics['latency_avg_seconds']:.3f}",
                f"- Latency p95 seconds: {metrics['latency_p95_seconds']:.3f}",
                f"- Send delay p95 seconds: {metrics['send_delay_p95_seconds']:.3f}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return metrics


def main() -> None:
    args = parse_args()
    metrics = asyncio.run(replay(args))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
