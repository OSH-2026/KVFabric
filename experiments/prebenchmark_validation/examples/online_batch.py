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

    if scenario.get("type") == "cache_pressure":
        return expand_cache_pressure_requests(scenario)
    if scenario.get("type") == "ambiguous_hot_revisit":
        return expand_ambiguous_hot_revisit_requests(scenario)
    if scenario.get("type") == "template_family_revisit":
        return expand_template_family_revisit_requests(scenario)
    if scenario.get("type") == "unique_cold":
        return expand_unique_cold_requests(scenario)
    if scenario.get("type") == "phased_hot_revisit":
        return expand_phased_hot_revisit_requests(scenario)
    if scenario.get("type") == "multi_hot_pressure":
        return expand_multi_hot_pressure_requests(scenario)

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


def expand_cache_pressure_requests(scenario: dict) -> list[dict]:
    hot_system = scenario["hot_shared_system"]
    hot_system += scenario.get("hot_shared_unit", "") * int(
        scenario.get("hot_shared_repeat", 1)
    )
    cold_unit = scenario["cold_unit"]
    hot_templates = scenario["hot_user_templates"]
    rounds = int(scenario.get("rounds", 1))
    hot_requests_per_round = int(scenario.get("hot_requests_per_round", 2))
    cold_requests_per_round = int(scenario.get("cold_requests_per_round", 4))
    cold_repeat = int(scenario.get("cold_repeat", 40))
    requests = []

    for round_index in range(rounds):
        for hot_index in range(hot_requests_per_round):
            template = hot_templates[hot_index % len(hot_templates)]
            requests.append(
                {
                    "messages": [
                        {"role": "system", "content": hot_system},
                        {
                            "role": "user",
                            "content": template.format(
                                round=round_index + 1,
                                index=hot_index + 1,
                            ),
                        },
                    ]
                }
            )

        for cold_index in range(cold_requests_per_round):
            cold_prefix = (
                f"冷长尾压力请求 round={round_index + 1} "
                f"index={cold_index + 1}。"
            )
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": cold_prefix + cold_unit * cold_repeat,
                        },
                        {
                            "role": "user",
                            "content": "用一句话回答：这个请求只用于冲刷 KV cache。",
                        },
                    ]
                }
            )

    return requests


def expand_phased_hot_revisit_requests(scenario: dict) -> list[dict]:
    hot_system = scenario["hot_shared_system"]
    hot_system += scenario.get("hot_shared_unit", "") * int(
        scenario.get("hot_shared_repeat", 1)
    )
    hot_template = scenario.get(
        "hot_user_template",
        "热点请求 {index}：用一句话解释热点前缀为什么值得保留。",
    )
    cold_unit = scenario["cold_unit"]
    warmup_hot_requests = int(scenario.get("warmup_hot_requests", 3))
    cold_pressure_requests = int(scenario.get("cold_pressure_requests", 96))
    revisit_hot_requests = int(scenario.get("revisit_hot_requests", 6))
    cold_repeat = int(scenario.get("cold_repeat", 20))
    requests = []

    def append_hot(phase: str, index: int) -> None:
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": hot_system},
                    {
                        "role": "user",
                        "content": hot_template.format(
                            phase=phase,
                            index=index,
                        ),
                    },
                ]
            }
        )

    for index in range(warmup_hot_requests):
        append_hot("warmup", index + 1)

    for index in range(cold_pressure_requests):
        cold_prefix = f"phased cold pressure request index={index + 1}。"
        requests.append(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": cold_prefix + cold_unit * cold_repeat,
                    },
                    {
                        "role": "user",
                        "content": "用一句话回答：这是阶段性冷长尾压力请求。",
                    },
                ]
            }
        )

    for index in range(revisit_hot_requests):
        append_hot("revisit", index + 1)

    return requests


def expand_ambiguous_hot_revisit_requests(scenario: dict) -> list[dict]:
    hot_system = scenario["hot_shared_system"]
    hot_system += scenario.get("hot_shared_unit", "") * int(
        scenario.get("hot_shared_repeat", 1)
    )
    hot_template = scenario.get(
        "hot_user_template",
        "{phase} 热点请求 {index}：用一句话解释热点前缀为什么值得保留。",
    )
    cold_anchor_unit = scenario["cold_anchor_unit"]
    cold_tail_unit = scenario["cold_tail_unit"]
    warmup_hot_requests = int(scenario.get("warmup_hot_requests", 4))
    cold_families = int(scenario.get("cold_families", 40))
    cold_variants_per_family = int(scenario.get("cold_variants_per_family", 3))
    revisit_hot_requests = int(scenario.get("revisit_hot_requests", 8))
    cold_anchor_repeat = int(scenario.get("cold_anchor_repeat", 12))
    cold_tail_repeat = int(scenario.get("cold_tail_repeat", 8))
    requests = []

    def append_hot(phase: str, index: int) -> None:
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": hot_system},
                    {
                        "role": "user",
                        "content": hot_template.format(
                            phase=phase,
                            index=index,
                        ),
                    },
                ]
            }
        )

    for index in range(warmup_hot_requests):
        append_hot("warmup", index + 1)

    for family in range(cold_families):
        cold_anchor = (
            f"ambiguous cold family {family + 1} shared-looking anchor。"
            "这段前缀在同一冷族内短暂重复，但后续不会回访。"
            + cold_anchor_unit * cold_anchor_repeat
        )
        for variant in range(cold_variants_per_family):
            cold_tail = (
                f" cold variant {variant + 1} unique tail。"
                + cold_tail_unit * cold_tail_repeat
            )
            requests.append(
                {
                    "messages": [
                        {"role": "system", "content": cold_anchor + cold_tail},
                        {
                            "role": "user",
                            "content": (
                                "用一句话回答：这是外形像热点、但不会长期回访的冷请求。"
                            ),
                        },
                    ]
                }
            )

    for index in range(revisit_hot_requests):
        append_hot("revisit", index + 1)

    return requests


def expand_multi_hot_pressure_requests(scenario: dict) -> list[dict]:
    hot_family_count = int(scenario.get("hot_family_count", 4))
    cycles = int(scenario.get("cycles", 4))
    cold_requests_after_hot = int(scenario.get("cold_requests_after_hot", 4))
    hot_shared_unit = scenario["hot_shared_unit"]
    hot_shared_repeat = int(scenario.get("hot_shared_repeat", 12))
    cold_unit = scenario["cold_unit"]
    cold_repeat = int(scenario.get("cold_repeat", 16))
    requests = []

    for cycle in range(cycles):
        for family in range(hot_family_count):
            family_prefix = (
                f"热点族 {family + 1} 的共享系统前缀。"
                "该前缀会跨多个 cycle 回访，用于测试 LRU 是否误驱逐。"
            )
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": family_prefix
                            + hot_shared_unit * hot_shared_repeat,
                        },
                        {
                            "role": "user",
                            "content": (
                                f"cycle {cycle + 1}, hot family {family + 1}: "
                                "用一句话说明热点前缀应被保留。"
                            ),
                        },
                    ]
                }
            )

            for cold_index in range(cold_requests_after_hot):
                cold_prefix = (
                    f"multi-hot 冷请求 cycle={cycle + 1} "
                    f"family={family + 1} index={cold_index + 1}。"
                )
                requests.append(
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": cold_prefix + cold_unit * cold_repeat,
                            },
                            {
                                "role": "user",
                                "content": "用一句话回答：这是冷长尾压力请求。",
                            },
                        ]
                    }
                )

    return requests


def expand_template_family_revisit_requests(scenario: dict) -> list[dict]:
    family_count = int(scenario.get("family_count", 8))
    warmup_per_family = int(scenario.get("warmup_per_family", 2))
    cold_pressure_requests = int(scenario.get("cold_pressure_requests", 96))
    revisit_per_family = int(scenario.get("revisit_per_family", 3))
    revisit_cycles = int(scenario.get("revisit_cycles", 1))
    template_unit = scenario["template_unit"]
    family_unit = scenario["family_unit"]
    cold_unit = scenario["cold_unit"]
    template_repeat = int(scenario.get("template_repeat", 8))
    family_repeat = int(scenario.get("family_repeat", 10))
    cold_repeat = int(scenario.get("cold_repeat", 18))
    requests = []

    def append_family_request(phase: str, family: int, index: int) -> None:
        shared_system = (
            f"KVFabric template family {family + 1}。"
            + template_unit * template_repeat
            + f"该请求属于长期回访模板族 {family + 1}。"
            + family_unit * family_repeat
        )
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": shared_system},
                    {
                        "role": "user",
                        "content": (
                            f"{phase} family={family + 1} index={index + 1}: "
                            "用一句话回答这个模板化多轮请求为什么应该复用历史 KV。"
                        ),
                    },
                ]
            }
        )

    for family in range(family_count):
        for index in range(warmup_per_family):
            append_family_request("warmup", family, index)

    for cycle in range(revisit_cycles):
        for index in range(cold_pressure_requests):
            requests.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                f"template cold pressure cycle={cycle + 1} "
                                f"index={index + 1}。"
                                + cold_unit * cold_repeat
                            ),
                        },
                        {
                            "role": "user",
                            "content": "用一句话回答：这是不会长期回访的普通冷请求。",
                        },
                    ]
                }
            )

        for family in range(family_count):
            for index in range(revisit_per_family):
                append_family_request(
                    f"revisit cycle={cycle + 1}", family, index
                )

    return requests


def expand_unique_cold_requests(scenario: dict) -> list[dict]:
    request_count = int(scenario.get("request_count", 120))
    cold_unit = scenario["cold_unit"]
    cold_repeat = int(scenario.get("cold_repeat", 14))
    requests = []
    for index in range(request_count):
        requests.append(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"ordinary unique request index={index + 1}。"
                            + cold_unit * cold_repeat
                        ),
                    },
                    {
                        "role": "user",
                        "content": "用一句话回答：这是普通无共享请求。",
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
