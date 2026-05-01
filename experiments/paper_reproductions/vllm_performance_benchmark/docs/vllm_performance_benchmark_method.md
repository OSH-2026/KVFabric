# vLLM Performance Benchmark — Methodology

> 本文档描述 vLLM 标准基础服务性能测试的方法论、指标定义和评测流程。

## 核心问题

本评测流程旨在回答以下三个问题：

1. **vLLM 在普通 serving 场景下性能是多少？**
   → 通过离线吞吐扫描，建立 (input_len × output_len) 矩阵的性能基线

2. **系统瓶颈主要在 prefill、decode、调度还是显存？**
   → 通过 KV cache 使用率、prompt/generation throughput 比值、GPU 显存分配来定位

3. **后续 KVCache 优化应优先降低 TTFT 还是提升吞吐？**
   → 通过 prefix cache A/B 对比和显存效率分析来回答

## 评测方法论

### 评测维度

| 维度 | 指标 | 采集方式 |
|------|------|---------|
| **吞吐** | req/s, tok/s (input/output/total) | `vllm bench throughput` 输出解析 |
| **显存** | 模型占用、KV cache 容量、KV cache 使用率 | vLLM 引擎日志 |
| **缓存效率** | Prefix cache hit rate | 引擎 `log-stats` 日志 |
| **延迟（待测）** | TTFT, TPOT, ITL, E2E Latency | `vllm bench serve`（需 bare-metal Linux） |

### 扫描矩阵设计

吞吐扫描通过 `configs/throughput_scan.json` 中的 `scan_points` 数组定义。每个扫描点包括：
- `input_len`：输入 prompt 长度（tokens）
- `output_len`：生成 token 数
- `num_prompts`：请求数（长序列用较少请求以避免 OOM）

完整矩阵覆盖从 128 tokens（短问答）到 2048 tokens（长上下文）的范围。

### Variant 系统

评测框架支持多 variant 对比：
- **vanilla_vllm**：官方 vLLM，prefix caching 关闭，作为性能基线
- **prefix_caching_on**：prefix caching 开启，用于测量 cache overhead 和复用收益

新增 variant 只需创建 `.env` 文件并在 plan 中注册。

## 输出指标说明

### 直接测量指标

| 指标 | 定义 | 单位 |
|------|------|------|
| `request_throughput` | 每秒完成的推理请求数 | req/s |
| `total_token_throughput` | 每秒处理的 input + output token 总数 | tok/s |
| `output_token_throughput` | 每秒生成的 output token 数 | tok/s |
| `kv_cache_tokens` | KV Cache 容量 | tokens |
| `kv_cache_memory_gib` | KV Cache 可用显存 | GiB |
| `kv_cache_usage_pct` | KV Cache 峰值使用率 | % |
| `prefix_cache_hit_rate_pct` | 前缀缓存命中率 | % |
| `model_memory_gib` | 模型权重显存占用 | GiB |
| `model_load_seconds` | 模型加载时间 | 秒 |

### 推导指标

| 指标 | 推导方式 |
|------|---------|
| Approx TTFT | `input_len / total_token_throughput`（仅粗略估计） |
| Approx TPOT | `1 / output_token_throughput`（仅粗略估计） |
| Memory efficiency | `KV cache tokens / (KV cache GiB * 1024³ / bytes_per_token)` |

## 环境要求

| 需求 | 说明 |
|------|------|
| NVIDIA GPU | 建议 8GB+ VRAM（RTX 4060 可运行 Qwen3.5-2B） |
| vLLM | >= 0.19.1 |
| Python | >= 3.10 |
| CUDA | >= 12.0 |

当前脚本通过项目级 `vllm_baseline/scripts/common.sh` 管理虚拟环境和路径。评测前需先运行 `setup_venv.sh` 和 `download_model.sh`。

## 与在线 Serving 评测的关系

离线吞吐（`vllm bench throughput`）和在线 Serving（`vllm bench serve`）回答不同的问题：

| 维度 | Offline Throughput | Online Serving |
|------|:---:|:---:|
| 运行模式 | 直接使用 `LLM` 引擎 | 通过 HTTP OpenAI-compatible API |
| 核心指标 | req/s, tok/s | TTFT, TPOT, ITL, E2E |
| GPU 使用率 | 接近 100%（持续批处理） | 取决于负载模式 |
| 适用场景 | 容量上限评估 | 用户体验延迟评估 |
| WSL2 兼容 | 正常 | 不可用（多进程 IPC 限制） |

两者互补：离线吞吐给上限，在线 Serving 给用户体验。

## 已知限制

1. **WSL2 环境**：`vllm bench serve` 不可用（HTTP API → EngineCore 多进程 IPC 失败），不可测量在线延迟
2. **8GB VRAM**：KV Cache 容量紧张（0.39-0.79 GiB），吞吐数据为同等硬件下的下限值
3. **随机数据集**：Prefix cache hit rate 为 0%（各 prompt 无共享前缀），需用 shared prefix 数据集测量真实复用收益
4. **评测耗时**：每次扫描需重新加载引擎（torch.compile 约 2 分钟），完整 suite 约 30-90 分钟
