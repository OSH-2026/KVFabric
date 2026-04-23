from __future__ import annotations

import argparse
from pathlib import Path

import torch
import vllm
from vllm import LLM, SamplingParams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local offline vLLM smoke test.")
    parser.add_argument("--model", required=True, help="Local model directory.")
    parser.add_argument(
        "--prompt",
        default="Explain KV cache in one short sentence.",
        help="Prompt used for the smoke test.",
    )
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.70)
    parser.add_argument("--max-model-len", type=int, default=1024)
    parser.add_argument("--max-num-seqs", type=int, default=1)
    parser.add_argument("--language-model-only", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model directory does not exist: {model_path}")

    print(f"vLLM version: {vllm.__version__}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"Loading local model: {model_path}", flush=True)

    llm = LLM(
        model=str(model_path),
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        max_num_seqs=args.max_num_seqs,
        language_model_only=args.language_model_only,
    )
    params = SamplingParams(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    outputs = llm.generate([args.prompt], params)

    print("PROMPT:", args.prompt)
    print("OUTPUT:", outputs[0].outputs[0].text.strip())


if __name__ == "__main__":
    main()
