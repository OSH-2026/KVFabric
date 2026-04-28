from __future__ import annotations

import argparse
import json
import platform
import shutil
import time
from pathlib import Path

import torch
import vllm
from vllm import LLM, SamplingParams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small offline vLLM batch.")
    parser.add_argument("--model", required=True, help="Local model directory.")
    parser.add_argument("--config", required=True, help="Experiment JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.70)
    parser.add_argument("--max-model-len", type=int, default=1024)
    parser.add_argument("--max-num-seqs", type=int, default=4)
    parser.add_argument("--language-model-only", action="store_true")
    prefix_group = parser.add_mutually_exclusive_group()
    prefix_group.add_argument("--enable-prefix-caching", action="store_true")
    prefix_group.add_argument("--no-enable-prefix-caching", action="store_true")
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, round((len(values) - 1) * pct))
    return values[index]


def main() -> None:
    args = parse_args()
    model_path = Path(args.model).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    prompts = config["prompts"]
    generation = config.get("generation", {})

    shutil.copy2(config_path, output_dir / "config.json")
    (output_dir / "env.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "vllm": vllm.__version__,
                "torch": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "model": str(model_path),
                "enable_prefix_caching_requested": args.enable_prefix_caching,
                "disable_prefix_caching_requested": args.no_enable_prefix_caching,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    llm_kwargs = {}
    if args.enable_prefix_caching:
        llm_kwargs["enable_prefix_caching"] = True
    elif args.no_enable_prefix_caching:
        llm_kwargs["enable_prefix_caching"] = False

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

    params = SamplingParams(
        temperature=float(generation.get("temperature", 0.0)),
        max_tokens=int(generation.get("max_tokens", 32)),
    )

    inference_started = time.perf_counter()
    outputs = llm.generate(prompts, params)
    inference_seconds = time.perf_counter() - inference_started
    total_seconds = time.perf_counter() - started

    prompt_tokens = 0
    output_tokens = 0
    raw_path = output_dir / "raw_outputs.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for item in outputs:
            generated = item.outputs[0]
            prompt_token_count = len(item.prompt_token_ids or [])
            output_token_count = len(generated.token_ids or [])
            prompt_tokens += prompt_token_count
            output_tokens += output_token_count
            raw_file.write(
                json.dumps(
                    {
                        "prompt": item.prompt,
                        "output": generated.text.strip(),
                        "prompt_tokens": prompt_token_count,
                        "output_tokens": output_token_count,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    metrics = {
        "requests": len(outputs),
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "total_seconds": total_seconds,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "output_tokens_per_second": output_tokens / inference_seconds
        if inference_seconds > 0
        else 0.0,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                f"# {config.get('name', 'offline_batch')}",
                "",
                f"- Requests: {metrics['requests']}",
                f"- Load seconds: {metrics['load_seconds']:.2f}",
                f"- Inference seconds: {metrics['inference_seconds']:.2f}",
                f"- Output tokens/s: {metrics['output_tokens_per_second']:.2f}",
                f"- Prompt tokens: {metrics['prompt_tokens']}",
                f"- Output tokens: {metrics['output_tokens']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

