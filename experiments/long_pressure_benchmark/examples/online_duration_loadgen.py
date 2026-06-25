from __future__ import annotations

import argparse
import asyncio
import json
import platform
import random
import statistics
import time
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "online_duration_loadgen.py requires httpx. Install it in the vLLM env."
    ) from exc

from online_batch import expand_requests, percentile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a duration-based async online vLLM load generator."
    )
    parser.add_argument("--config", required=True, help="Experiment JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", required=True)
    parser.add_argument("--duration-seconds", type=float, default=3600.0)
    parser.add_argument("--warmup-seconds", type=float, default=60.0)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--metrics-interval", type=float, default=30.0)
    parser.add_argument("--raw-sample-rate", type=float, default=0.01)
    parser.add_argument("--raw-sample-limit", type=int, default=2000)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument(
        "--request-selection",
        choices=("sequential", "shuffle", "random"),
        default=None,
        help=(
            "How duration runs select from the expanded payload pool. "
            "Defaults to config.loadgen.request_selection or sequential."
        ),
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        help="Seed for shuffle/random request selection and raw sampling.",
    )
    parser.add_argument(
        "--disable-kvfabric-headers",
        action="store_true",
        help="Do not forward request meta as x-kvfabric-* headers.",
    )
    return parser.parse_args()


class RunStats:
    def __init__(self, started: float) -> None:
        self.started = started
        self.completed = 0
        self.errors = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.latencies: list[float] = []
        self.recent_latencies: deque[float] = deque(maxlen=4096)
        self.sampled_outputs = 0
        self.goodput_prompt_tokens = 0
        self.goodput_completion_tokens = 0
        self.goodput_total_tokens = 0
        self.class_stats: dict[str, dict[str, Any]] = defaultdict(
            self._new_bucket
        )
        self.segment_stats: dict[str, dict[str, Any]] = defaultdict(
            self._new_bucket
        )

    @staticmethod
    def _new_bucket() -> dict[str, Any]:
        return {
            "completed": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "goodput_prompt_tokens": 0,
            "goodput_completion_tokens": 0,
            "goodput_total_tokens": 0,
            "latencies": [],
            "recent_latencies": deque(maxlen=1024),
        }

    @staticmethod
    def _record_bucket(
        bucket: dict[str, Any],
        latency: float,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        slo_pass: bool,
    ) -> None:
        bucket["completed"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_tokens"] += total_tokens
        if slo_pass:
            bucket["goodput_prompt_tokens"] += prompt_tokens
            bucket["goodput_completion_tokens"] += completion_tokens
            bucket["goodput_total_tokens"] += total_tokens
        bucket["latencies"].append(latency)
        bucket["recent_latencies"].append(latency)

    def record_success(
        self,
        latency: float,
        usage: dict[str, Any],
        request_class: str,
        segment: str,
        slo_seconds: float,
    ) -> None:
        self.completed += 1
        self.latencies.append(latency)
        self.recent_latencies.append(latency)
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        slo_pass = slo_seconds <= 0 or latency <= slo_seconds
        if slo_pass:
            self.goodput_prompt_tokens += prompt_tokens
            self.goodput_completion_tokens += completion_tokens
            self.goodput_total_tokens += total_tokens

        self._record_bucket(
            self.class_stats[request_class],
            latency,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            slo_pass,
        )
        self._record_bucket(
            self.segment_stats[segment],
            latency,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            slo_pass,
        )

    def record_error(self, request_class: str, segment: str) -> None:
        self.errors += 1
        self.class_stats[request_class]["errors"] += 1
        self.segment_stats[segment]["errors"] += 1

    def snapshot(self, now: float) -> dict[str, Any]:
        elapsed = max(now - self.started, 1e-9)
        recent = list(self.recent_latencies)
        return {
            "elapsed_seconds": elapsed,
            "completed": self.completed,
            "errors": self.errors,
            "requests_per_second": self.completed / elapsed,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_tokens_per_second": self.prompt_tokens / elapsed,
            "completion_tokens_per_second": self.completion_tokens / elapsed,
            "total_tokens_per_second": self.total_tokens / elapsed,
            "goodput_prompt_tokens": self.goodput_prompt_tokens,
            "goodput_completion_tokens": self.goodput_completion_tokens,
            "goodput_total_tokens": self.goodput_total_tokens,
            "goodput_total_tokens_per_second": (
                self.goodput_total_tokens / elapsed
            ),
            "latency_avg_seconds": statistics.mean(recent) if recent else 0.0,
            "latency_p50_seconds": percentile(recent, 0.50),
            "latency_p95_seconds": percentile(recent, 0.95),
            "class_metrics": self.class_snapshot(elapsed),
        }

    def class_snapshot(self, elapsed: float) -> dict[str, Any]:
        return self._bucket_snapshot(self.class_stats, elapsed, recent=True)

    def _bucket_snapshot(
        self,
        buckets: dict[str, dict[str, Any]],
        elapsed: float,
        recent: bool = False,
    ) -> dict[str, Any]:
        output = {}
        for name, stats in sorted(buckets.items()):
            latencies = (
                list(stats["recent_latencies"])
                if recent
                else list(stats["latencies"])
            )
            completed = int(stats["completed"])
            output[name] = {
                "completed": completed,
                "errors": int(stats["errors"]),
                "requests_per_second": completed / elapsed,
                "prompt_tokens": int(stats["prompt_tokens"]),
                "completion_tokens": int(stats["completion_tokens"]),
                "total_tokens": int(stats["total_tokens"]),
                "prompt_tokens_per_second": int(stats["prompt_tokens"]) / elapsed,
                "completion_tokens_per_second": (
                    int(stats["completion_tokens"]) / elapsed
                ),
                "total_tokens_per_second": int(stats["total_tokens"]) / elapsed,
                "goodput_prompt_tokens": int(stats["goodput_prompt_tokens"]),
                "goodput_completion_tokens": int(
                    stats["goodput_completion_tokens"]
                ),
                "goodput_total_tokens": int(stats["goodput_total_tokens"]),
                "goodput_total_tokens_per_second": (
                    int(stats["goodput_total_tokens"]) / elapsed
                ),
                "latency_avg_seconds": statistics.mean(latencies)
                if latencies
                else 0.0,
                "latency_p50_seconds": percentile(latencies, 0.50),
                "latency_p95_seconds": percentile(latencies, 0.95),
                "latency_p99_seconds": percentile(latencies, 0.99),
            }
        return output

    def final_class_metrics(self, elapsed: float) -> dict[str, Any]:
        return self._bucket_snapshot(self.class_stats, elapsed)

    def final_segment_metrics(
        self,
        segment_elapsed: dict[str, float],
    ) -> dict[str, Any]:
        output = {}
        for name, stats in sorted(self.segment_stats.items()):
            elapsed = max(segment_elapsed.get(name, 0.0), 1e-9)
            output[name] = self._bucket_snapshot({name: stats}, elapsed)[name]
        return output


def build_segments(
    config: dict[str, Any],
    duration_seconds: float,
    fallback_concurrency: int,
) -> list[dict[str, Any]]:
    loadgen = config.get("loadgen", {})
    configured = loadgen.get("segments") or []
    if not configured:
        return [
            {
                "name": "main",
                "start": 0.0,
                "end": duration_seconds,
                "duration": duration_seconds,
                "concurrency": fallback_concurrency,
                "score": True,
            }
        ]

    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for item in configured:
        duration = float(item.get("duration_seconds", 0.0))
        if duration <= 0:
            continue
        name = str(item.get("name", f"segment_{len(segments)}"))
        concurrency = int(item.get("concurrency", fallback_concurrency))
        segments.append(
            {
                "name": name,
                "start": cursor,
                "end": cursor + duration,
                "duration": duration,
                "concurrency": max(concurrency, 1),
                "score": bool(item.get("score", True)),
            }
        )
        cursor += duration
    if not segments:
        raise ValueError("loadgen.segments was present but empty after parsing.")
    return segments


def active_segment(
    segments: list[dict[str, Any]],
    elapsed: float,
) -> dict[str, Any]:
    for segment in segments:
        if segment["start"] <= elapsed < segment["end"]:
            return segment
    return segments[-1]


def segment_elapsed_map(
    segments: list[dict[str, Any]],
    total_elapsed: float,
) -> dict[str, float]:
    output: dict[str, float] = {}
    for segment in segments:
        elapsed = max(
            min(total_elapsed, float(segment["end"])) - float(segment["start"]),
            0.0,
        )
        output[str(segment["name"])] = elapsed
    return output


class PayloadSelector:
    def __init__(
        self,
        payloads: list[dict[str, Any]],
        mode: str,
        rng: random.Random,
    ) -> None:
        self.payloads = payloads
        self.mode = mode
        self.rng = rng
        self.order = list(range(len(payloads)))
        self.position = 0
        self.epoch = 0
        if mode == "shuffle":
            self.rng.shuffle(self.order)

    def select(self, request_no: int) -> dict[str, Any]:
        if self.mode == "random":
            return self.payloads[self.rng.randrange(len(self.payloads))]
        if self.mode == "shuffle":
            if self.position >= len(self.order):
                self.position = 0
                self.epoch += 1
                self.rng.shuffle(self.order)
            index = self.order[self.position]
            self.position += 1
            return self.payloads[index]
        return self.payloads[request_no % len(self.payloads)]


def build_payloads(config: dict[str, Any], model: str) -> list[dict[str, Any]]:
    generation = config.get("generation", {})
    payloads = []
    for index, item in enumerate(expand_requests(config)):
        meta = item.get("meta", {})
        max_tokens = int(
            item.get("max_tokens")
            or meta.get("max_tokens")
            or generation.get("max_tokens", 32)
        )
        payloads.append(
            {
                "index": index,
                "meta": meta,
                "payload": {
                    "model": model,
                    "messages": item["messages"],
                    "temperature": float(generation.get("temperature", 0.0)),
                    "max_tokens": max_tokens,
                },
            }
        )
    if not payloads:
        raise ValueError("Config expanded to zero requests.")
    return payloads


def _meta_value(meta: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = meta.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _derive_reuse_and_priority(request_class: str, burst: bool) -> tuple[str, str]:
    normalized = request_class.lower().replace("-", "_")
    if "hot" in normalized:
        return "durable", "high"
    if "ambiguous" in normalized or "transient" in normalized:
        return "transient", "normal"
    if burst and "cold" in normalized:
        return "none", "bypass"
    if "cold" in normalized or "unique" in normalized:
        return "none", "low"
    return "unknown", "normal"


def build_kvfabric_headers(meta: dict[str, Any]) -> dict[str, str]:
    request_class = _meta_value(meta, "class", "request_class") or "unclassified"
    burst = bool(meta.get("burst", False)) or "burst" in request_class
    expected_reuse, cache_priority = _derive_reuse_and_priority(
        request_class,
        burst,
    )

    headers = {
        "x-kvfabric-request-class": request_class,
        "x-kvfabric-cache-priority": _meta_value(
            meta,
            "cache_priority",
            "priority",
        )
        or cache_priority,
        "x-kvfabric-expected-reuse": _meta_value(
            meta,
            "expected_reuse",
            "reuse",
        )
        or expected_reuse,
        "x-kvfabric-burst": "true" if burst else "false",
    }
    tenant = _meta_value(meta, "tenant_id", "tenant")
    family = _meta_value(meta, "family_id", "family")
    phase = _meta_value(meta, "phase")
    segment = _meta_value(meta, "segment")
    session = _meta_value(meta, "session_id", "session")
    turn = _meta_value(meta, "turn_index", "turn")
    slo_ms = _meta_value(meta, "slo_ms")
    if tenant is not None:
        headers["x-kvfabric-tenant-id"] = tenant
    if family is not None:
        headers["x-kvfabric-family-id"] = family
    if phase is not None:
        headers["x-kvfabric-phase"] = phase
    elif segment is not None:
        headers["x-kvfabric-phase"] = segment
    if session is not None:
        headers["x-kvfabric-session-id"] = session
    if turn is not None:
        headers["x-kvfabric-turn-index"] = turn
    if slo_ms is not None:
        headers["x-kvfabric-slo-ms"] = slo_ms
    return headers


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


async def worker(
    worker_id: int,
    client: httpx.AsyncClient,
    url: str,
    payloads: list[dict[str, Any]],
    selector: PayloadSelector,
    stats: RunStats,
    stats_lock: asyncio.Lock,
    index_lock: asyncio.Lock,
    raw_file: Any,
    raw_sample_rate: float,
    raw_sample_limit: int,
    timeout: float,
    stop_time: float,
    max_requests: int,
    counter: dict[str, int],
    sample_rng: random.Random,
    kvfabric_headers_enabled: bool,
    segments: list[dict[str, Any]],
    run_started: float,
    slo_seconds: float,
) -> None:
    while time.perf_counter() < stop_time:
        now = time.perf_counter()
        elapsed = max(now - run_started, 0.0)
        segment = active_segment(segments, elapsed)
        segment_name = str(segment["name"])
        if worker_id >= int(segment["concurrency"]):
            await asyncio.sleep(0.05)
            continue
        async with index_lock:
            if max_requests > 0 and counter["issued"] >= max_requests:
                return
            request_no = counter["issued"]
            counter["issued"] += 1
            item = selector.select(request_no)
        request_meta = dict(item.get("meta", {}))
        request_meta["segment"] = segment_name
        request_class = str(request_meta.get("class", "unclassified"))
        headers = (
            build_kvfabric_headers(request_meta)
            if kvfabric_headers_enabled
            else None
        )
        try:
            latency, data = await post_chat(
                client,
                url,
                item["payload"],
                headers,
                timeout,
            )
            usage = data.get("usage", {})
            should_sample = (
                raw_sample_rate >= 1.0
                or sample_rng.random() < raw_sample_rate
            )
            async with stats_lock:
                stats.record_success(
                    latency,
                    usage,
                    request_class,
                    segment_name,
                    slo_seconds,
                )
                if should_sample and stats.sampled_outputs < raw_sample_limit:
                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    raw_file.write(
                        json.dumps(
                            {
                                "worker_id": worker_id,
                                "request_no": request_no,
                                "source_index": item["index"],
                                "meta": request_meta,
                                "segment": segment_name,
                                "kvfabric_headers": headers or {},
                                "latency_seconds": latency,
                                "usage": usage,
                                "output": message.get("content", ""),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    stats.sampled_outputs += 1
        except Exception as exc:  # noqa: BLE001
            async with stats_lock:
                stats.record_error(request_class, segment_name)
                raw_file.write(
                    json.dumps(
                        {
                            "worker_id": worker_id,
                            "request_no": request_no,
                            "source_index": item["index"],
                            "meta": request_meta,
                            "segment": segment_name,
                            "kvfabric_headers": headers or {},
                            "error": repr(exc),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )


def select_prometheus_lines(text: str) -> list[str]:
    needles = (
        "kv_cache",
        "prefix",
        "gpu_cache",
        "cache_config",
        "num_requests",
    )
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
    stop_time: float,
) -> None:
    rolling_path = output_dir / "rolling_metrics.jsonl"
    prometheus_path = output_dir / "prometheus_cache_samples.jsonl"
    with rolling_path.open("w", encoding="utf-8") as rolling_file, (
        prometheus_path.open("w", encoding="utf-8")
    ) as prometheus_file:
        while time.perf_counter() < stop_time:
            await asyncio.sleep(interval)
            now = time.perf_counter()
            async with stats_lock:
                snapshot = stats.snapshot(now)
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


async def run(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    loadgen_config = config.get("loadgen", {})
    configured_concurrency = args.concurrency or int(config.get("concurrency", 1))
    request_selection = args.request_selection or str(
        loadgen_config.get("request_selection", "sequential")
    )
    if request_selection not in {"sequential", "shuffle", "random"}:
        raise ValueError(f"Invalid request_selection={request_selection}")
    random_seed = (
        args.random_seed
        if args.random_seed is not None
        else int(loadgen_config.get("random_seed", 0))
    )
    selector_rng = random.Random(random_seed)
    sample_rng = random.Random(random_seed + 1)
    payloads = build_payloads(config, args.model)
    selector = PayloadSelector(payloads, request_selection, selector_rng)
    kvfabric_headers_enabled = not args.disable_kvfabric_headers
    segments = build_segments(
        config,
        args.duration_seconds,
        configured_concurrency,
    )
    total_segment_duration = max(float(segment["end"]) for segment in segments)
    effective_duration = min(args.duration_seconds, total_segment_duration)
    concurrency = max(int(segment["concurrency"]) for segment in segments)
    slo_seconds = float(loadgen_config.get("slo_seconds", 0.0))
    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    metrics_url = f"http://{args.host}:{args.port}/metrics"
    started = time.perf_counter()
    stop_time = started + effective_duration
    stats = RunStats(started=started)
    stats_lock = asyncio.Lock()
    index_lock = asyncio.Lock()
    counter = {"issued": 0}

    (output_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "env.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "host": args.host,
                "port": args.port,
                "model": args.model,
                "concurrency": concurrency,
                "configured_concurrency": configured_concurrency,
                "duration_seconds": effective_duration,
                "requested_duration_seconds": args.duration_seconds,
                "warmup_seconds": args.warmup_seconds,
                "segments": segments,
                "slo_seconds": slo_seconds,
                "payload_pool_size": len(payloads),
                "max_requests": args.max_requests,
                "request_selection": request_selection,
                "random_seed": random_seed,
                "payload_classes": summarize_payload_classes(payloads),
                "kvfabric_headers_enabled": kvfabric_headers_enabled,
                "kvfabric_header_summary": summarize_kvfabric_headers(payloads)
                if kvfabric_headers_enabled
                else {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    limits = httpx.Limits(
        max_connections=max(concurrency * 2, 16),
        max_keepalive_connections=max(concurrency, 8),
    )
    async with httpx.AsyncClient(limits=limits) as client:
        with (output_dir / "raw_outputs_sample.jsonl").open(
            "w", encoding="utf-8"
        ) as raw_file:
            workers = [
                asyncio.create_task(
                    worker(
                        worker_id=worker_id,
                        client=client,
                        url=url,
                        payloads=payloads,
                        selector=selector,
                        stats=stats,
                        stats_lock=stats_lock,
                        index_lock=index_lock,
                        raw_file=raw_file,
                        raw_sample_rate=args.raw_sample_rate,
                        raw_sample_limit=args.raw_sample_limit,
                        timeout=args.timeout,
                        stop_time=stop_time,
                        max_requests=args.max_requests,
                        counter=counter,
                        sample_rng=sample_rng,
                        kvfabric_headers_enabled=kvfabric_headers_enabled,
                        segments=segments,
                        run_started=started,
                        slo_seconds=slo_seconds,
                    )
                )
                for worker_id in range(concurrency)
            ]
            sampler = asyncio.create_task(
                metrics_sampler(
                    client=client,
                    metrics_url=metrics_url,
                    stats=stats,
                    stats_lock=stats_lock,
                    output_dir=output_dir,
                    interval=args.metrics_interval,
                    stop_time=stop_time,
                )
            )
            await asyncio.gather(*workers)
            await sampler

    total_seconds = max(time.perf_counter() - started, 1e-9)
    async with stats_lock:
        latencies = stats.latencies
        metrics = {
            **stats.snapshot(time.perf_counter()),
            "requests": stats.completed,
            "issued_requests": counter["issued"],
            "payload_pool_size": len(payloads),
            "concurrency": concurrency,
            "total_seconds": total_seconds,
            "warmup_seconds": args.warmup_seconds,
            "segments": segments,
            "slo_seconds": slo_seconds,
            "errors": stats.errors,
            "goodput_prompt_tokens": stats.goodput_prompt_tokens,
            "goodput_completion_tokens": stats.goodput_completion_tokens,
            "goodput_total_tokens": stats.goodput_total_tokens,
            "goodput_total_tokens_per_second": (
                stats.goodput_total_tokens / total_seconds
            ),
            "latency_avg_seconds": statistics.mean(latencies) if latencies else 0.0,
            "latency_p50_seconds": percentile(latencies, 0.50),
            "latency_p95_seconds": percentile(latencies, 0.95),
            "latency_p99_seconds": percentile(latencies, 0.99),
            "request_selection": request_selection,
            "random_seed": random_seed,
            "class_metrics": stats.final_class_metrics(total_seconds),
            "segment_metrics": stats.final_segment_metrics(
                segment_elapsed_map(segments, total_seconds)
            ),
        }

    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "class_metrics.json").write_text(
        json.dumps(metrics["class_metrics"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "segment_metrics.json").write_text(
        json.dumps(metrics["segment_metrics"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                f"# {config.get('name', 'online_duration_loadgen')}",
                "",
                f"- Duration seconds: {metrics['total_seconds']:.2f}",
                f"- Requests: {metrics['requests']}",
                f"- Errors: {metrics['errors']}",
                f"- Payload pool size: {metrics['payload_pool_size']}",
                f"- Concurrency: {metrics['concurrency']}",
                f"- Segments: {json.dumps(segments, ensure_ascii=False)}",
                f"- SLO seconds: {metrics['slo_seconds']:.2f}",
                f"- Request selection: {metrics['request_selection']}",
                f"- Random seed: {metrics['random_seed']}",
                f"- KVFabric headers: {kvfabric_headers_enabled}",
                f"- Requests/s: {metrics['requests_per_second']:.3f}",
                f"- Prompt tokens/s: {metrics['prompt_tokens_per_second']:.2f}",
                f"- Completion tokens/s: {metrics['completion_tokens_per_second']:.2f}",
                f"- Total tokens/s: {metrics['total_tokens_per_second']:.2f}",
                f"- Goodput tokens/s: {metrics['goodput_total_tokens_per_second']:.2f}",
                f"- Latency avg seconds: {metrics['latency_avg_seconds']:.2f}",
                f"- Latency p50 seconds: {metrics['latency_p50_seconds']:.2f}",
                f"- Latency p95 seconds: {metrics['latency_p95_seconds']:.2f}",
                f"- Latency p99 seconds: {metrics['latency_p99_seconds']:.2f}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return metrics


def summarize_payload_classes(payloads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in payloads:
        request_class = str(item.get("meta", {}).get("class", "unclassified"))
        counts[request_class] += 1
    return dict(sorted(counts.items()))


def summarize_kvfabric_headers(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    priority_counts: dict[str, int] = defaultdict(int)
    reuse_counts: dict[str, int] = defaultdict(int)
    with_family = 0
    with_tenant = 0
    for item in payloads:
        headers = build_kvfabric_headers(item.get("meta", {}))
        priority_counts[headers.get("x-kvfabric-cache-priority", "unknown")] += 1
        reuse_counts[headers.get("x-kvfabric-expected-reuse", "unknown")] += 1
        if "x-kvfabric-family-id" in headers:
            with_family += 1
        if "x-kvfabric-tenant-id" in headers:
            with_tenant += 1
    return {
        "priority_counts": dict(sorted(priority_counts.items())),
        "reuse_counts": dict(sorted(reuse_counts.items())),
        "with_family": with_family,
        "with_tenant": with_tenant,
    }


def main() -> None:
    args = parse_args()
    metrics = asyncio.run(run(args))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
