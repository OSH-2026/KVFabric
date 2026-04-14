# vLLM Bring-up Log (2026-04-14)

## Summary

- Status: `passed`
- Goal: configure `vLLM` locally inside the project workspace and complete both offline and online smoke tests.
- Result:
  - `vLLM 0.19.0` installed successfully in a fresh project-local `.venv`
  - local Qwen model downloaded into project-local cache
  - offline inference passed
  - OpenAI-compatible serving passed

## Environment

- OS: `Ubuntu 24.04.1 LTS` on `WSL2`
- Kernel: `Linux 6.6.87.2-microsoft-standard-WSL2`
- Python: `3.12.3`
- GPU: `NVIDIA GeForce RTX 4070 Laptop GPU (8 GiB)`
- NVIDIA driver: `581.83`
- PyTorch: `2.10.0+cu129`
- vLLM: `0.19.0`

## Local layout

- Virtual environment: `.venv/`
- vLLM cache: `.cache/vllm/`
- Hugging Face cache: `.cache/huggingface/`
- Local model path: `.cache/models/Qwen2.5-0.5B-Instruct/`

## Install path used

Official package sources were used for the Python environment:

```bash
python3 -m venv .venv
env HTTP_PROXY=http://172.30.208.1:7897 \
    HTTPS_PROXY=http://172.30.208.1:7897 \
    ALL_PROXY=http://172.30.208.1:7897 \
    PIP_DEFAULT_TIMEOUT=120 \
    ./.venv/bin/pip install vllm --extra-index-url https://download.pytorch.org/whl/cu129
```

Health check:

```bash
./.venv/bin/python -c "import vllm, torch; print(vllm.__version__); print(torch.__version__); print(torch.cuda.is_available())"
```

Observed result:

- `vllm 0.19.0`
- `torch 2.10.0+cu129`
- `torch.cuda.is_available() == True`

## Model download notes

Direct `huggingface_hub` downloads were unreliable in this WSL + proxy setup because metadata `HEAD` requests to `huggingface.co` frequently timed out or returned `504`.

To keep using the official Hugging Face source, the model files were fetched with direct `GET` requests into a local model directory:

```bash
mkdir -p .cache/models/Qwen2.5-0.5B-Instruct
cd .cache/models/Qwen2.5-0.5B-Instruct

for f in config.json generation_config.json merges.txt model.safetensors tokenizer.json tokenizer_config.json vocab.json; do
  env HTTP_PROXY=http://172.30.208.1:7897 \
      HTTPS_PROXY=http://172.30.208.1:7897 \
      ALL_PROXY=http://172.30.208.1:7897 \
      curl -L --http1.1 --retry 8 --retry-all-errors --retry-delay 2 -C - \
      -o "$f" "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main/$f"
done
```

Downloaded local model footprint:

- total directory size: about `954 MiB`
- main weights file: `model.safetensors` about `943 MiB`

## Offline smoke test

Because `vLLM` detects WSL and forces multiprocessing `spawn`, launching `LLM(...)` from a `python - <<'PY'` stdin script fails with:

```text
FileNotFoundError: ... '/home/.../<stdin>'
```

Workaround used:

- store the smoke test in a real file: `logs/vllm_offline_smoke.py`

Run command:

```bash
env VLLM_CACHE_ROOT=.cache/vllm \
    ./.venv/bin/python logs/vllm_offline_smoke.py
```

Observed result:

- local model loaded successfully
- attention backend selected: `FLASH_ATTN`
- model load memory reported by vLLM: about `0.93 GiB`
- available KV cache memory reported by vLLM: about `4.36 GiB`
- sample output:

```text
PROMPT: Explain KV cache in one short sentence.
OUTPUT: A cache is a temporary storage area in a computer's memory that stores frequently accessed data, allowing for faster access and reducing the need for full disk reads.
```

## Online serving smoke test

Server command:

```bash
./.venv/bin/vllm serve .cache/models/Qwen2.5-0.5B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.70 \
  --max-num-seqs 1 \
  --served-model-name qwen-local-0.5b
```

Verification commands:

```bash
curl -s http://127.0.0.1:8000/v1/models
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen-local-0.5b","messages":[{"role":"user","content":"Reply with exactly five English words about KV cache."}],"temperature":0.0,"max_tokens":16}'
```

Observed result:

- `/v1/models` returned the served model entry `qwen-local-0.5b`
- `/v1/chat/completions` returned a valid chat completion JSON payload
- serving endpoint confirmed working on `http://127.0.0.1:8000`

## WSL-specific notes discovered

- vLLM forces `VLLM_WORKER_MULTIPROC_METHOD=spawn` on WSL.
- Inline stdin Python scripts are not suitable for offline `LLM(...)` tests under this mode.
- vLLM warns that WSL uses `pin_memory=False`, which may reduce performance.
- There is an NCCL cleanup warning at process exit if the quick smoke script ends immediately; it did not block inference.

## Recommended next steps

1. Keep this local Qwen model as the minimum reproducible smoke-test artifact.
2. Re-run the same server command and start tracing the `scheduler / prefix cache / paged attention / hybrid cache` code paths.
3. Add a second benchmark-oriented run with a slightly larger public model only after the current 0.5B path is stable.
