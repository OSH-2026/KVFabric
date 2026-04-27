from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small online vLLM batch.")
    parser.add_argument("--config", required=True, help="Experiment JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", required=True)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, round((len(values) - 1) * pct))
    return values[index]


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    return {"latency_seconds": time.perf_counter() - started, "response": data}


def expand_requests(config: dict) -> list[dict]:
    if "requests" in config:
        return config["requests"]

    scenario = config.get("scenario")
    if not scenario:
        raise ValueError("Config must contain either 'requests' or 'scenario'.")

    shared_system = scenario.get("shared_system", "")
    if "shared_system_unit" in scenario:
        shared_system += scenario["shared_system_unit"] * int(
            scenario.get("shared_system_repeat", 1)
        )
    user_templates = scenario["user_templates"]
    repeat = int(scenario.get("repeat", 1))
    requests = []
    for round_index in range(repeat):
        for template_index, template in enumerate(user_templates):
            requests.append(
                {
                    "messages": [
                        {"role": "system", "content": shared_system},
                        {
                            "role": "user",
                            "content": template.format(
                                round=round_index + 1,
                                index=template_index + 1,
                            ),
                        },
                    ]
                }
            )
    return requests


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    generation = config.get("generation", {})
    requests = expand_requests(config)
    concurrency = args.concurrency or int(config.get("concurrency", 1))
    url = f"http://{args.host}:{args.port}/v1/chat/completions"

    shutil.copy2(config_path, output_dir / "config.json")
    (output_dir / "env.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "host": args.host,
                "port": args.port,
                "model": args.model,
                "concurrency": concurrency,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payloads = []
    for item in requests:
        payloads.append(
            {
                "model": args.model,
                "messages": item["messages"],
                "temperature": float(generation.get("temperature", 0.0)),
                "max_tokens": int(generation.get("max_tokens", 32)),
            }
        )

    started = time.perf_counter()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_index = {
            executor.submit(post_json, url, payload, args.timeout): index
            for index, payload in enumerate(payloads)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            result = future.result()
            result["index"] = index
            results.append(result)
    total_seconds = time.perf_counter() - started

    results.sort(key=lambda item: item["index"])
    latencies = [item["latency_seconds"] for item in results]
    raw_path = output_dir / "raw_outputs.jsonl"
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for payload, result in zip(payloads, results, strict=True):
            choice = result["response"]["choices"][0]
            usage = result["response"].get("usage", {})
            prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            total_tokens += int(usage.get("total_tokens", 0) or 0)
            raw_file.write(
                json.dumps(
                    {
                        "messages": payload["messages"],
                        "output": choice["message"]["content"],
                        "latency_seconds": result["latency_seconds"],
                        "usage": usage,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    metrics = {
        "requests": len(results),
        "concurrency": concurrency,
        "total_seconds": total_seconds,
        "requests_per_second": len(results) / total_seconds
        if total_seconds > 0
        else 0.0,
        "latency_avg_seconds": statistics.mean(latencies) if latencies else 0.0,
        "latency_p50_seconds": percentile(latencies, 0.50),
        "latency_p95_seconds": percentile(latencies, 0.95),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "completion_tokens_per_second": completion_tokens / total_seconds
        if total_seconds > 0
        else 0.0,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                f"# {config.get('name', 'online_batch')}",
                "",
                f"- Requests: {metrics['requests']}",
                f"- Concurrency: {metrics['concurrency']}",
                f"- Total seconds: {metrics['total_seconds']:.2f}",
                f"- Requests/s: {metrics['requests_per_second']:.2f}",
                f"- Latency avg seconds: {metrics['latency_avg_seconds']:.2f}",
                f"- Latency p50 seconds: {metrics['latency_p50_seconds']:.2f}",
                f"- Latency p95 seconds: {metrics['latency_p95_seconds']:.2f}",
                f"- Prompt tokens: {metrics['prompt_tokens']}",
                f"- Completion tokens: {metrics['completion_tokens']}",
                f"- Completion tokens/s: {metrics['completion_tokens_per_second']:.2f}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
