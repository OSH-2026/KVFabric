from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
import vllm
from vllm import LLM, SamplingParams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an offline KVCache quality evaluation suite."
    )
    parser.add_argument("--model", required=True, help="Local model directory.")
    parser.add_argument("--suite-config", required=True, help="Suite JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    parser.add_argument("--variant-name", required=True, help="Variant label.")
    parser.add_argument("--variant-description", default="", help="Variant notes.")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.70)
    parser.add_argument("--max-model-len", type=int, default=1024)
    parser.add_argument("--max-num-seqs", type=int, default=1)
    parser.add_argument("--language-model-only", action="store_true")
    prefix_group = parser.add_mutually_exclusive_group()
    prefix_group.add_argument("--enable-prefix-caching", action="store_true")
    prefix_group.add_argument("--no-enable-prefix-caching", action="store_true")
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def score_output(output: str, scoring: dict[str, Any]) -> tuple[float, bool, str]:
    mode = scoring["mode"]
    normalized = normalize_text(output)

    if mode == "contains_all":
        keywords = [normalize_text(item) for item in scoring["keywords"]]
        matched = [item for item in keywords if item in normalized]
        score = len(matched) / len(keywords) if keywords else 0.0
        return score, score == 1.0, f"matched={len(matched)}/{len(keywords)}"

    if mode == "contains_any":
        keywords = [normalize_text(item) for item in scoring["keywords"]]
        passed = any(item in normalized for item in keywords)
        return (1.0 if passed else 0.0), passed, "contains_any"

    if mode == "exact":
        expected = normalize_text(scoring["expected"])
        passed = normalized == expected
        return (1.0 if passed else 0.0), passed, "exact"

    if mode == "regex":
        pattern = scoring["pattern"]
        passed = re.search(pattern, output, flags=re.MULTILINE) is not None
        return (1.0 if passed else 0.0), passed, "regex"

    raise ValueError(f"Unsupported scoring mode: {mode}")


def summarize_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    score_sum = sum(row["score"] for row in rows)
    pass_count = sum(1 for row in rows if row["passed"])
    return {
        "items": total,
        "avg_score": score_sum / total if total else 0.0,
        "pass_rate": pass_count / total if total else 0.0,
        "pass_count": pass_count,
    }


def main() -> None:
    args = parse_args()

    model_path = Path(args.model).expanduser().resolve()
    suite_config_path = Path(args.suite_config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    suite_config = json.loads(suite_config_path.read_text(encoding="utf-8"))
    task_file = suite_config_path.parent / suite_config["task_file"]
    tasks_payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = tasks_payload["items"]
    generation = suite_config.get("generation", {})

    shutil.copy2(suite_config_path, output_dir / "config.json")
    shutil.copy2(task_file, output_dir / "tasks.json")

    env_info: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "vllm": vllm.__version__,
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "model": str(model_path),
        "variant_name": args.variant_name,
        "variant_description": args.variant_description,
        "enable_prefix_caching_requested": args.enable_prefix_caching,
        "disable_prefix_caching_requested": args.no_enable_prefix_caching,
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "max_num_seqs": args.max_num_seqs,
    }

    before_free = None
    total_gpu_memory = None
    if torch.cuda.is_available():
        before_free, total_gpu_memory = torch.cuda.mem_get_info()
        env_info["gpu_total_bytes"] = total_gpu_memory
        env_info["gpu_free_before_load_bytes"] = before_free

    (output_dir / "env.json").write_text(
        json.dumps(env_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    llm_kwargs: dict[str, Any] = {}
    if args.enable_prefix_caching:
        llm_kwargs["enable_prefix_caching"] = True
    elif args.no_enable_prefix_caching:
        llm_kwargs["enable_prefix_caching"] = False

    prompts = [task["prompt"] for task in tasks]

    started = time.perf_counter()
    llm = LLM(
        model=str(model_path),
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        max_num_seqs=args.max_num_seqs,
        language_model_only=args.language_model_only,
        **llm_kwargs,
    )
    load_seconds = time.perf_counter() - started

    after_load_free = None
    if torch.cuda.is_available():
        after_load_free, _ = torch.cuda.mem_get_info()

    params = SamplingParams(
        temperature=float(generation.get("temperature", 0.0)),
        max_tokens=int(generation.get("max_tokens", 96)),
    )

    inference_started = time.perf_counter()
    outputs = llm.generate(prompts, params)
    inference_seconds = time.perf_counter() - inference_started
    total_seconds = time.perf_counter() - started

    after_generate_free = None
    if torch.cuda.is_available():
        after_generate_free, _ = torch.cuda.mem_get_info()

    prompt_tokens = 0
    output_tokens = 0
    raw_path = output_dir / "raw_outputs.jsonl"
    scored_path = output_dir / "item_scores.jsonl"

    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    overall_rows: list[dict[str, Any]] = []

    with raw_path.open("w", encoding="utf-8") as raw_file, scored_path.open(
        "w", encoding="utf-8"
    ) as scored_file:
        for task, item in zip(tasks, outputs, strict=True):
            generated = item.outputs[0]
            output_text = generated.text.strip()
            prompt_token_count = len(item.prompt_token_ids or [])
            output_token_count = len(generated.token_ids or [])
            prompt_tokens += prompt_token_count
            output_tokens += output_token_count

            score, passed, detail = score_output(output_text, task["scoring"])
            row = {
                "id": task["id"],
                "category": task["category"],
                "score": score,
                "passed": passed,
                "detail": detail,
                "reference_answer": task.get("reference_answer", ""),
                "prompt_tokens": prompt_token_count,
                "output_tokens": output_token_count,
            }
            category_rows[task["category"]].append(row)
            overall_rows.append(row)

            raw_file.write(
                json.dumps(
                    {
                        "id": task["id"],
                        "category": task["category"],
                        "prompt": task["prompt"],
                        "output": output_text,
                        "reference_answer": task.get("reference_answer", ""),
                        "prompt_tokens": prompt_token_count,
                        "output_tokens": output_token_count,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            scored_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    category_summary = {
        category: summarize_category(rows)
        for category, rows in sorted(category_rows.items())
    }
    overall_summary = summarize_category(overall_rows)

    metrics: dict[str, Any] = {
        "variant_name": args.variant_name,
        "suite_name": suite_config.get("name", "quality_suite"),
        "tasks": len(tasks),
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "total_seconds": total_seconds,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "output_tokens_per_second": output_tokens / inference_seconds
        if inference_seconds > 0
        else 0.0,
        "overall_avg_score": overall_summary["avg_score"],
        "overall_pass_rate": overall_summary["pass_rate"],
        "overall_pass_count": overall_summary["pass_count"],
        "category_summary": category_summary,
    }

    if (
        torch.cuda.is_available()
        and before_free is not None
        and after_load_free is not None
        and after_generate_free is not None
        and total_gpu_memory is not None
    ):
        metrics["gpu_free_before_load_bytes"] = before_free
        metrics["gpu_free_after_load_bytes"] = after_load_free
        metrics["gpu_free_after_generate_bytes"] = after_generate_free
        metrics["gpu_used_delta_load_bytes"] = before_free - after_load_free
        metrics["gpu_used_delta_generate_bytes"] = max(
            0, after_load_free - after_generate_free
        )
        metrics["gpu_total_bytes"] = total_gpu_memory

    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary_lines = [
        f"# {args.variant_name}",
        "",
        f"- Tasks: {metrics['tasks']}",
        f"- Load seconds: {metrics['load_seconds']:.2f}",
        f"- Inference seconds: {metrics['inference_seconds']:.2f}",
        f"- Output tokens/s: {metrics['output_tokens_per_second']:.2f}",
        f"- Overall avg score: {metrics['overall_avg_score']:.3f}",
        f"- Overall pass rate: {metrics['overall_pass_rate']:.3f}",
        "",
        "## Category Summary",
        "",
    ]

    for category, summary in category_summary.items():
        summary_lines.append(
            f"- {category}: avg_score={summary['avg_score']:.3f}, pass_rate={summary['pass_rate']:.3f}, items={summary['items']}"
        )

    (output_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
