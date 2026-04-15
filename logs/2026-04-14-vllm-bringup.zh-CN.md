# vLLM 启动与打通日志（2026-04-14）

[English](2026-04-14-vllm-bringup.md)|[中文](2026-04-14-vllm-bringup.zh-CN.md)

## 概要

- 状态：`passed`
- 目标：在项目工作区内本地配置 `vLLM`，并完成 offline 与 online 两条 smoke test。
- 结果：
  - 在新的项目本地 `.venv` 中成功安装 `vLLM 0.19.0`
  - 将本地 Qwen 模型下载到项目本地缓存
  - offline 推理验证通过
  - OpenAI 兼容服务验证通过

## 环境

- 操作系统：`WSL2` 上的 `Ubuntu 24.04.1 LTS`
- 内核：`Linux 6.6.87.2-microsoft-standard-WSL2`
- Python：`3.12.3`
- GPU：`NVIDIA GeForce RTX 4070 Laptop GPU (8 GiB)`
- NVIDIA 驱动：`581.83`
- PyTorch：`2.10.0+cu129`
- vLLM：`0.19.0`

## 本地目录布局

- 虚拟环境：`.venv/`
- vLLM 缓存：`.cache/vllm/`
- Hugging Face 缓存：`.cache/huggingface/`
- 本地模型路径：`.cache/models/Qwen2.5-0.5B-Instruct/`

## 实际安装路径

Python 环境使用了官方包源：

```bash
python3 -m venv .venv
env HTTP_PROXY=http://172.30.208.1:7897 \
    HTTPS_PROXY=http://172.30.208.1:7897 \
    ALL_PROXY=http://172.30.208.1:7897 \
    PIP_DEFAULT_TIMEOUT=120 \
    ./.venv/bin/pip install vllm --extra-index-url https://download.pytorch.org/whl/cu129
```

健康检查：

```bash
./.venv/bin/python -c "import vllm, torch; print(vllm.__version__); print(torch.__version__); print(torch.cuda.is_available())"
```

观测结果：

- `vllm 0.19.0`
- `torch 2.10.0+cu129`
- `torch.cuda.is_available() == True`

## 模型下载说明

在该 WSL + 代理环境下，直接使用 `huggingface_hub` 下载不稳定，因为对 `huggingface.co` 发起的元数据 `HEAD` 请求经常超时或返回 `504`。

为继续使用官方 Hugging Face 源，改为在本地模型目录内直接用 `GET` 请求拉取模型文件：

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

本地模型体积：

- 目录总大小：约 `954 MiB`
- 主权重文件：`model.safetensors` 约 `943 MiB`

## Offline Smoke Test

由于 `vLLM` 在 WSL 下会强制使用多进程 `spawn`，因此用 `python - <<'PY'` 这种 stdin 脚本方式启动 `LLM(...)` 会失败，报错如下：

```text
FileNotFoundError: ... '/home/.../<stdin>'
```

采用的绕过方案：

- 将 smoke test 写入实际文件：`logs/vllm_offline_smoke.py`

运行命令：

```bash
env VLLM_CACHE_ROOT=.cache/vllm \
    ./.venv/bin/python logs/vllm_offline_smoke.py
```

观测结果：

- 本地模型加载成功
- attention 后端选择为：`FLASH_ATTN`
- vLLM 报告的模型加载显存：约 `0.93 GiB`
- vLLM 报告的可用 KV cache 显存：约 `4.36 GiB`
- 样例输出：

```text
PROMPT: Explain KV cache in one short sentence.
OUTPUT: A cache is a temporary storage area in a computer's memory that stores frequently accessed data, allowing for faster access and reducing the need for full disk reads.
```

## Online Serving Smoke Test

服务启动命令：

```bash
./.venv/bin/vllm serve .cache/models/Qwen2.5-0.5B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.70 \
  --max-num-seqs 1 \
  --served-model-name qwen-local-0.5b
```

验证命令：

```bash
curl -s http://127.0.0.1:8000/v1/models
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen-local-0.5b","messages":[{"role":"user","content":"Reply with exactly five English words about KV cache."}],"temperature":0.0,"max_tokens":16}'
```

观测结果：

- `/v1/models` 返回了服务模型条目 `qwen-local-0.5b`
- `/v1/chat/completions` 返回了合法的 chat completion JSON
- 服务端点在 `http://127.0.0.1:8000` 验证可用

## WSL 特定现象

- vLLM 在 WSL 下会强制设置 `VLLM_WORKER_MULTIPROC_METHOD=spawn`。
- 在该模式下，不适合使用内联 stdin Python 脚本做 offline `LLM(...)` 测试。
- vLLM 会警告 WSL 使用 `pin_memory=False`，可能影响性能。
- 若 smoke 脚本立即退出，会出现 NCCL 清理警告，但不影响本次推理通过。

## 后续建议

1. 保留该本地 Qwen 模型，作为最小可复现 smoke-test 工件。
2. 使用相同服务命令重跑，并开始追踪 `scheduler / prefix cache / paged attention / hybrid cache` 代码路径。
3. 在当前 0.5B 链路稳定后，再补一组略大公开模型的对照测试。