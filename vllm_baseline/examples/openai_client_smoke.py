from __future__ import annotations

import argparse

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use the OpenAI-compatible vLLM endpoint for a simple chat smoke test."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--prompt",
        default="Reply with one short sentence about KV cache.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = OpenAI(
        base_url=f"http://{args.host}:{args.port}/v1",
        api_key="EMPTY",
    )

    models = client.models.list()
    print("MODELS:")
    for item in models.data:
        print(f"  - {item.id}")

    response = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "user", "content": args.prompt}],
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    print("PROMPT:", args.prompt)
    print("RESPONSE:", response.choices[0].message.content)


if __name__ == "__main__":
    main()
