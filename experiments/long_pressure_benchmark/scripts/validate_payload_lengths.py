#!/usr/bin/env python3
"""Validate generated long-pressure payload sizes before launching a run."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from experiments.long_pressure_benchmark.examples.online_batch import (  # noqa: E402
    expand_requests,
)


def request_max_tokens(item: dict[str, Any], default_max_tokens: int) -> int:
    value = item.get("meta", {}).get("max_tokens", default_max_tokens)
    return int(value)


def prompt_char_count(item: dict[str, Any]) -> int:
    return sum(len(message.get("content", "")) for message in item["messages"])


def prompt_token_count(tokenizer: Any, item: dict[str, Any]) -> int:
    tokens = tokenizer.apply_chat_template(
        item["messages"],
        tokenize=True,
        add_generation_prompt=True,
    )
    if isinstance(tokens, Mapping) or (
        hasattr(tokens, "__contains__") and "input_ids" in tokens
    ):
        tokens = tokens["input_ids"]
    if hasattr(tokens, "shape"):
        return int(tokens.shape[-1])
    if tokens and isinstance(tokens[0], list):
        return len(tokens[0])
    return len(tokens)


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    return int(statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--tokenizer", default="")
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--sample-limit", type=int, default=0)
    parser.add_argument(
        "--tokenize-top-per-class",
        type=int,
        default=0,
        help="With a tokenizer, validate only the longest N char-sized payloads per class.",
    )
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    requests = expand_requests(config)
    generated_requests = len(requests)
    if args.sample_limit > 0:
        requests = requests[: args.sample_limit]
    default_max_tokens = int(config.get("generation", {}).get("max_tokens", 64))

    tokenizer = None
    if args.tokenizer:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            args.tokenizer,
            trust_remote_code=False,
        )

    by_class: dict[str, list[int]] = {}
    violations: list[dict[str, Any]] = []
    max_row: dict[str, Any] | None = None

    indexed_requests = list(enumerate(requests))
    if tokenizer is not None and args.tokenize_top_per_class > 0:
        grouped: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
        for index, item in indexed_requests:
            request_class = str(item.get("meta", {}).get("class", "unclassified"))
            total_chars = prompt_char_count(item) + request_max_tokens(
                item,
                default_max_tokens,
            )
            grouped.setdefault(request_class, []).append((total_chars, index, item))
        selected: list[tuple[int, dict[str, Any]]] = []
        for rows in grouped.values():
            rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
            selected.extend((index, item) for _, index, item in rows[: args.tokenize_top_per_class])
        indexed_requests = sorted(selected, key=lambda row: row[0])

    for index, item in indexed_requests:
        request_class = str(item.get("meta", {}).get("class", "unclassified"))
        max_tokens = request_max_tokens(item, default_max_tokens)
        prompt_size = (
            prompt_token_count(tokenizer, item)
            if tokenizer is not None
            else prompt_char_count(item)
        )
        total_size = prompt_size + max_tokens
        by_class.setdefault(request_class, []).append(total_size)
        row = {
            "index": index,
            "class": request_class,
            "prompt_size": prompt_size,
            "max_tokens": max_tokens,
            "total_size": total_size,
            "meta": item.get("meta", {}),
        }
        if max_row is None or total_size > int(max_row["total_size"]):
            max_row = row
        if tokenizer is not None and total_size > args.max_model_len:
            violations.append(row)

    result = {
        "config": args.config,
        "generated_requests": generated_requests,
        "validated_requests": len(indexed_requests),
        "unit": "tokens" if tokenizer is not None else "chars",
        "max_model_len": args.max_model_len if tokenizer is not None else None,
        "max_row": max_row,
        "violations": len(violations),
        "classes": {
            name: {
                "count": len(values),
                "p50_total": percentile(values, 50),
                "p95_total": percentile(values, 95),
                "p99_total": percentile(values, 99),
                "max_total": max(values) if values else 0,
            }
            for name, values in sorted(by_class.items())
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    if violations:
        print(json.dumps({"first_violations": violations[:10]}, indent=2, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
