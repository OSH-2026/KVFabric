from pathlib import Path

from vllm import LLM, SamplingParams


MODEL_PATH = Path(__file__).resolve().parents[1] / ".cache" / "models" / "Qwen2.5-0.5B-Instruct"
PROMPT = "Explain KV cache in one short sentence."


def main() -> None:
    print(f"Loading local model: {MODEL_PATH}", flush=True)
    llm = LLM(
        model=str(MODEL_PATH),
        gpu_memory_utilization=0.70,
        max_model_len=1024,
        max_num_seqs=1,
    )
    params = SamplingParams(temperature=0.0, max_tokens=32)
    outputs = llm.generate([PROMPT], params)
    print("PROMPT:", PROMPT)
    print("OUTPUT:", outputs[0].outputs[0].text.strip())


if __name__ == "__main__":
    main()
