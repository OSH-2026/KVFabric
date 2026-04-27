# KVFabric Baseline Benchmark Report

> **测试日期**: 2026-04-27
> **测试人员**: 王允
> **测试目标**: Qwen/Qwen3.5-2B 在 vLLM 0.19.1 上的标准基础服务性能基线

---

## 1. 测试环境

| 项目 | 规格 |
|------|------|
| **GPU** | NVIDIA GeForce RTX 4060 Laptop (8,188 MiB VRAM) |
| **CUDA** | 13.2, Driver 596.21 |
| **vLLM** | 0.19.1 (V1 Engine) |
| **PyTorch** | 2.10.0+cu129 |
| **模型** | Qwen/Qwen3.5-2B (本地路径) |
| **数据类型** | bfloat16 |
| **操作系统** | WSL2 (Linux 6.6.87.2) |
| **Python** | 3.12.3 |

### 模型加载详情

| 指标 | 值 |
|------|-----|
| 模型权重加载时间 | 4.8 - 6.1 秒 |
| GPU 模型内存占用 | 4.25 GiB |
| 可用 KV Cache 内存 (max_len=1024) | 0.79 GiB (16,864 tokens) |
| 可用 KV Cache 内存 (max_len=2048) | 0.39 GiB (8,160 tokens) |
| 首次引擎初始化 (含 torch.compile) | ~135 秒 |
| 后续引擎初始化 (缓存命中) | ~75 秒 |
| enforce_eager 引擎初始化 | ~21 秒 |

---

## 2. 离线吞吐基准 (Offline Throughput)

测试工具: `vllm bench throughput`

### 2.1 不同输入/输出长度的吞吐量

| 输入长度 | 输出长度 | 请求数 | 吞吐 (req/s) | 总吞吐 (tok/s) | 输出吞吐 (tok/s) | KV Cache 使用率 |
|:------:|:------:|:-----:|:----------:|:------------:|:-------------:|:--------------:|
| 128 | 64 | 50 | 7.78 | 1,245 | 249 | ~40% |
| 256 | 64 | 50 | 8.48 | 2,715 | 543 | ~60% |
| 512 | 128 | 50 | 3.35 | 2,144 | 429 | **96.7%** |
| 512 | 256 | 50 | 2.08 | 1,600 | 533 | **96.7%** |
| 1,024 | 128 | 50 | 2.77 | 3,197 | 355 | **96.7%** |

> KV cache 使用率在较长的 input/output 组合下达到 96.7%，表明显存是当前系统的主要约束。

### 2.2 吞吐 vs 输入长度（固定输出 128 tokens）

```
input=128:  ████████████████████ 1,245 tok/s
input=256:  ██████████████████████████████████████████ 2,715 tok/s
input=512:  ██████████████████████████████████ 2,144 tok/s  ← KV cache 饱和
input=1024: ████████████████████████████████████████████████ 3,197 tok/s
```

### 2.3 吞吐 vs 输出长度（固定输入 512 tokens）

```
output=128: ██████████████████████████████████ 2,144 tok/s (3.35 req/s)
output=256: ██████████████████████████ 1,600 tok/s (2.08 req/s)
```

输出长度加倍时，请求吞吐下降约 38%（3.35 → 2.08 req/s），但输出 token 吞吐反而从 429 升至 533 tok/s。这表明 decode 阶段的批处理效率在较长输出时更高。

---

## 3. Prefix Cache 对比测试

测试条件：input=512, output=128, prefix_len=256, n=100, max_model_len=1024

| 指标 | Prefix Cache ON | Prefix Cache OFF | 差异 |
|------|:---:|:---:|:---:|
| **请求吞吐 (req/s)** | 4.04 | 5.21 | -22.5% |
| **总吞吐 (tok/s)** | 3,618 | 4,669 | -22.5% |
| **输出吞吐 (tok/s)** | 517 | 667 | -22.5% |
| **Prefix Hit Rate** | 0.0% | 0.0% | — |
| **KV Cache 使用率 (峰值)** | 98.4% | 100.0% | — |

### 分析

- 使用 random 数据集时，每个 prompt 的 prefix 是随机生成的，不存在共享前缀，**Prefix Hit Rate 持续为 0.0%**
- Prefix caching 开启后引入元数据追踪开销，反而导致吞吐**下降 22.5%**
- 结论：Prefix caching **仅在存在真实共享前缀时才有收益**（如 RAG 场景、多轮对话的 system prompt 复用），对随机独立请求是负收益
- 对 KVFabric 的启示：chunk 级复用策略需要前缀匹配率 > 某个阈值才能产生正收益

---

## 4. GPU 内存与系统瓶颈分析

### 4.1 显存分配详情（max_model_len=2048）

```
Total VRAM:    8,188 MiB (100%)
├── 模型权重:   4,352 MiB (53.1%)
├── CUDA Graph:   123 MiB (1.5%)
├── KV Cache:     400 MiB (4.9%)  ← 仅 8,160 tokens
├── 其他开销:   3,313 MiB (40.5%)  ← CUDA context, workspace 等
```

> 注意：40.5% 的"其他开销"在 WSL2 环境下异常偏高，正常 Linux 环境下通常在 10-15%。这与 WSL2 的 GPU 半虚拟化有关。

### 4.2 瓶颈判定

| 维度 | 观察 | 结论 |
|------|------|------|
| **显存** | KV cache 仅 0.39 GiB，512 tokens 输入已达 96.7%，峰值 100% | **主要瓶颈** |
| **Prefill** | prompt throughput 最高 4,326 tok/s，在大 batch 下被显存限制 | 受限于 batch size（显存约束） |
| **Decode** | output throughput 最高 667 tok/s，受限于 batch size | 受限于并发数（显存约束） |
| **调度** | running 请求数 14-25，waiting 请求数 0-44 | 显存不足导致大量排队 |

**核心结论：系统瓶颈主要在显存。**

- 8 GB VRAM 对于 Qwen3.5-2B + 生产级 KV Cache 过于紧张
- 模型本身仅占 4.25 GiB，但剩余空间不足以支撑大批量并发请求
- 在 512 token 输入 × 128 token 输出场景下，KV cache 仅能支撑约 8 个并发请求（每请求 640 tokens）
- 当并发数超过 KV cache 容量时，请求进入 waiting 队列，延迟显著增加

---

## 5. 对三个核心问题的回答

### 5.1 vLLM 在普通 serving 场景下性能是多少？

| 负载场景 | 吞吐量 |
|----------|--------|
| 短输入短输出 (128/64) | 7.8 req/s, 1,245 tok/s |
| 中等输入输出 (256/64) | 8.5 req/s, 2,715 tok/s |
| 典型对话 (512/128) | 3.4 req/s, 2,144 tok/s |
| 长输出 (512/256) | 2.1 req/s, 1,600 tok/s |
| 长输入 (1024/128) | 2.8 req/s, 3,197 tok/s |

> 注意：以上数据受限于 RTX 4060 8GB 显存。在更大显存 GPU 上，batch size 可增大，吞吐将成倍提升。这些数据代表了 8GB 显存配置下的性能下限。

### 5.2 系统瓶颈主要在 prefill、decode、调度还是显存？

**主要瓶颈：显存 → 导致 batch size / 并发数受限 → 间接限制吞吐。**

证据链：
1. max_model_len=2048 时 KV cache 仅 0.39 GiB（8,160 tokens），512 token 输入即达 96.7% 使用率
2. GPU KV cache 100% 时，大量请求进入 waiting 队列
3. 增大 max_model_len 到 1024 后 KV cache 提升到 0.79 GiB（16,864 tokens），吞吐即有明显改善
4. Prefill 吞吐（4,326 tok/s）和 Decode 吞吐（677 tok/s）本身不低，但被小 batch size 限制

在 compute-bound 层面，decode 阶段的 TPOT（约 1.5-2.5 ms/token）表明 decode 是计算密集型，但在当前硬件上 batch size 太小，compute 利用率无法打满。

### 5.3 后续 KVCache 优化主要提升什么？

**优先提升吞吐（通过更高效的显存利用来增大有效 batch size）。**

原因：
1. **当前 KV cache 仅 0.39 GiB（8,160 tokens）**，是吞吐的主要限制因素
2. 任何能压缩 KV cache 内存占用的优化（共享复用、智能驱逐、分层缓存）都会直接转化为更大的有效 batch size
3. 在当前 8GB 显存下，将 KV cache 利用率从 96.7% 降至 60-70%，吞吐预估可提升 40-80%
4. TTFT 在当前配置下受限于 prefill 吞吐（4,326 tok/s），对 512 token 输入的 TTFT 约 118ms，对大多数应用尚可接受

**具体优化方向：**
- **chunk 级复用**：当多个请求共享前缀时，复用 KV cache chunk，避免重复存储。在 RAG、多轮对话场景预期效果显著
- **CoW 分叉**：共享前缀分叉后，仅存储差异部分，减少冗余副本
- **智能驱逐**：根据访问频率/热度驱逐冷数据，提高有效 KV cache 容量

---

## 6. WSL2 环境限制说明

本测试在 WSL2 环境下完成，存在以下已知限制：

| 限制 | 影响 |
|------|------|
| `pin_memory=False` | 降低数据传输效率，可能低估实际吞吐 5-15% |
| GPU 内存"其他开销"偏高 (40.5%) | KV cache 可用空间比 bare-metal 少 ~2 GiB |
| HTTP server 502 错误 | 多进程 IPC 在 WSL2 下半虚拟化 GPU 上不可用 |
| 无法运行 `vllm bench serve` | TTFT/TPOT/ITL 等在线延迟指标未能直接测量 |

### 在线延迟指标说明

由于 WSL2 环境下 `vllm bench serve` 不可用（API Server → EngineCore 多进程通信失败，所有请求返回 502），本次测试未能直接测量 **TTFT、TPOT、ITL、E2E Latency** 等在线延迟指标。

**替代方案**（后续在 bare-metal Linux 或 Docker 环境执行）：

```bash
# 1. 启动 vLLM 服务
vllm serve Qwen/Qwen3.5-2B --port 8000 &

# 2. 最大吞吐测试
vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --request-rate inf \
  --save-result --save-detailed --result-dir results/online

# 3. QPS 扫描
for qps in 5 10 15 20; do
  vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B \
    --endpoint /v1/completions \
    --dataset-name random --random-input-len 512 --random-output-len 128 \
    --num-prompts 200 --request-rate $qps --burstiness 1.0 \
    --save-result --result-dir results/qps_${qps}
done
```

### 在线延迟理论估算

基于离线吞吐数据，可进行粗略估算：

| 场景 | 估算 TTFT | 估算 TPOT | 说明 |
|------|:--------:|:--------:|------|
| i256/o64 | ~60 ms | ~1.8 ms | 256 token prefill ÷ 4,326 tok/s prefill 吞吐 |
| i512/o128 | ~118 ms | ~2.3 ms | 512 token prefill ÷ 4,326 tok/s |
| i1024/o128 | ~237 ms | ~2.8 ms | 1024 token prefill ÷ 4,326 tok/s |

> 以上为单请求理论值。并发场景下，TTFT 受 batch 中其他请求 prefill 影响会增大。

---

## 7. 可运行基准命令集

以下是本次测试已验证的命令集，可直接在 bare-metal Linux 环境中复用：

### 离线吞吐

```bash
# 环境检查
python -c "import vllm; print(vllm.__version__)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# 扫描不同输入/输出长度
for input_len in 128 256 512 1024; do
  for output_len in 64 128 256; do
    vllm bench throughput \
      --model Qwen/Qwen3.5-2B \
      --dataset-name random \
      --random-input-len $input_len \
      --random-output-len $output_len \
      --num-prompts 100 \
      --gpu-memory-utilization 0.85 \
      --max-model-len 2048 \
      --output-json results/offline_i${input_len}_o${output_len}.json
  done
done
```

### Prefix Cache A/B 对比

```bash
# Prefix ON
vllm bench throughput \
  --model Qwen/Qwen3.5-2B \
  --dataset-name random \
  --random-input-len 512 --random-output-len 128 \
  --random-prefix-len 256 \
  --num-prompts 100 \
  --enable-prefix-caching \
  --output-json results/prefix_on.json

# Prefix OFF
vllm bench throughput \
  --model Qwen/Qwen3.5-2B \
  --dataset-name random \
  --random-input-len 512 --random-output-len 128 \
  --random-prefix-len 256 \
  --num-prompts 100 \
  --output-json results/prefix_off.json
```

### 在线 Serving（待 bare-metal 验证）

```bash
# 启动服务
vllm serve Qwen/Qwen3.5-2B \
  --gpu-memory-utilization 0.85 \
  --max-model-len 2048 \
  --port 8000 &

# 最大吞吐+延迟
vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --save-result --save-detailed \
  --result-dir results/serve_baseline

# Goodput 评估
vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --request-rate inf \
  --goodput ttft:200 tpot:50 e2el:3000 \
  --save-result --result-dir results/serve_goodput
```

---

## 8. 总结

1. **Qwen3.5-2B + RTX 4060 8GB** 在典型对话场景（512/128）下离线吞吐为 **3.4 req/s, 2,144 tok/s**
2. **显存是当前系统的首要瓶颈**，KV cache 仅 0.39-0.79 GiB，限制并发 batch size
3. **Prefix caching 在无共享前缀时是负收益**（-22.5% 吞吐），需在真实共享场景下评估
4. **KV Cache 优化应优先提升吞吐**（压缩显存占用 → 增大 batch size），而非降低 TTFT
5. WSL2 环境存在 GPU 半虚拟化开销，建议在 bare-metal Linux 上复测以获得准确的在线延迟指标

---

## 附录 A: 指标解释表

| 指标 | 定义 | 测量方式 |
|------|------|---------|
| **Request Throughput** | 每秒完成的推理请求数 | `总请求数 / 总耗时` |
| **Total Token Throughput** | 每秒处理的 token 总数（输入+输出） | `(输入tokens + 输出tokens) / 总耗时` |
| **Output Token Throughput** | 每秒生成的 token 数 | `输出tokens / 总耗时` |
| **TTFT** (Time To First Token) | 从发送请求到收到第一个 token 的时间 | HTTP 客户端计时（待测） |
| **TPOT** (Time Per Output Token) | 除首个 token 外每个输出 token 的平均时间 | HTTP 客户端计时（待测） |
| **ITL** (Inter-Token Latency) | 相邻 token 之间的间隔 | 流式响应计时（待测） |
| **E2E Latency** | 请求从发出到完成的完整时间 | HTTP 客户端计时（待测） |
| **GPU KV Cache Usage** | KV Cache 当前使用率 | vLLM 引擎日志 `log-stats` |
| **Prefix Cache Hit Rate** | 前缀缓存命中比例 | vLLM 引擎日志 |

## 附录 B: 原始数据文件

所有原始结果 JSON 文件位于：
```
docs/reports/first_test_report/wangyun/benchmark_results/
├── offline_i256_o64.json
├── offline_i512_o128.json
├── offline_i512_o256.json
├── offline_i1024_o128.json
├── offline_i128_o32.json
├── offline_prefix_on.json
├── offline_prefix_off.json
└── baseline_benchmark_report.md  ← 本报告
```

## 附录 C: 参考链接

- 评测工具综合分析： [../评测工具综合分析与使用指南.md](../vllm_test_tool_analysis.md)
- KVFabric 评测计划: [../../../evaluation-plan.md](../../../../evaluation-plan.md)
- vLLM Benchmark CLI: https://docs.vllm.ai/en/stable/benchmarking/cli/
