# KVFabric 评测工具综合分析与使用指南

> 本文整合了 vLLM bench、inference-perf、Vidur 三套 LLM 推理评测工具的技术分析与实战指南。
> 目标：为 KVFabric 项目的标准基础服务性能评测提供完整的方法论与可操作命令集。

---

## 目录

- [1. 任务背景与目标](#1-任务背景与目标)
- [2. 资料入口与工具总览](#2-资料入口与工具总览)
- [3. vLLM bench 深度分析](#3-vllm-bench-深度分析)
- [4. inference-perf 深度分析](#4-inference-perf-深度分析)
- [5. Vidur 深度分析](#5-vidur-深度分析)
- [6. 三工具分工与推荐流水线](#6-三工具分工与推荐流水线)
- [7. KVFabric 实战指南](#7-kvfabric-实战指南)
- [8. 附录](#8-附录)

---

## 1. 任务背景与目标

### 1.1 任务定义

对 vLLM 的标准基础服务性能进行评测，跑通核心基准测试，记录不同输入/输出长度、并发数下的性能变化，并回答以下三个核心问题：

1. vLLM 在普通 serving 场景下的性能区间是多少
2. 系统瓶颈主要在 prefill、decode、调度还是显存
3. 后续 KV Cache 优化应优先降低首 token 延迟还是提升吞吐

### 1.2 分析资料

| 资料 | 入口 |
|------|------|
| vLLM benchmark 文档 | https://docs.vllm.ai/en/stable/benchmarking/cli/ |
| vLLM benchmark README | https://github.com/vllm-project/vllm/blob/main/benchmarks/README.md |
| inference-perf | https://github.com/kubernetes-sigs/inference-perf |
| Vidur 论文 | MLSys'24: _VIDUR: A Large-Scale Simulation Framework for LLM Inference_ ([arXiv 2405.05465](https://arxiv.org/abs/2405.05465)) |

### 1.3 预期产出

- 一组可运行的 vLLM benchmark 命令
- baseline_benchmark_method 报告
- 指标解释表和基础结果表

---

## 2. 资料入口与工具总览

### 2.1 资料状态说明

- `docs.vllm.ai/en/stable/contributing/benchmarks.html` 当前跳转到贡献主页，实际 benchmark CLI 文档入口为 https://docs.vllm.ai/en/stable/benchmarking/cli/
- vLLM benchmark README 是概要性重定向页面，详细的脚本参数和方法论在 CLI 文档中
- vLLM 官方建议：生产服务器评测推荐使用 [GuideLLM](https://github.com/vllm-project/guidellm)，因其负载模式更灵活、支持实时进度与自动报告

### 2.2 三类工具的定位

四份资料对应三个不同层级的评测工具：

| 工具 | 定位 | 核心价值 |
|------|------|---------|
| **vLLM bench** | 单引擎、快速、特性回归导向 | 在线/离线基准 + 丰富数据集 |
| **inference-perf** | 跨引擎、SLO/Goodput/流量建模导向 | 生产级评测平台 |
| **Vidur** | 仿真与配置搜索导向 | 低成本探索大配置空间 |

### 2.3 总览对比

| 维度 | vLLM bench | inference-perf | Vidur |
|------|-----------|----------------|-------|
| **运行方式** | `vllm bench serve/throughput` CLI | pip / Docker / K8s | `python -m vidur.main` |
| **需要 GPU** | 是 | 是（压测客户端不需要） | 否（仅一次 profiling 需 GPU） |
| **覆盖引擎** | 仅 vLLM | vLLM / SGLang / TGI / 任何 OpenAI 兼容端点 | 内置模型库（Llama/Qwen/InternLM 等） |
| **核心指标** | TTFT / TPOT / ITL / throughput | TTFT / TPOT / ITL / NTPOT / Goodput / $/M tokens | TTFT / TPOT / E2E / Batch Size |
| **流量建模** | Poisson / Gamma burst / ramp-up | constant / Poisson / concurrent / trace replay | Poisson / trace replay |
| **SLO/Goodput** | `--goodput` 参数 | 完整 Goodput 框架 + 自动报告 | 无 |
| **KVFabric 阶段** | Phase 1 基线 / Phase 2 回归 | Phase 2 生产验证 | Phase 1 瓶颈分析 / Phase 2 what-if |
| **复杂度** | 低（随 vLLM 安装） | 中（需独立安装） | 中（需一次 profiling） |

---

## 3. vLLM bench 深度分析

### 3.1 工具定位

`vllm bench` 是 vLLM 官方自带的性能评测 CLI，随 vLLM 安装即用。文档明确其定位为"评估 vLLM 特定特性和回归测试"，**偏研发回归**而非完整生产评估。

benchmark README 将能力分为四层：
- **Serving benchmarks**：在线推理性能（latency、throughput）
- **Throughput benchmarks**：离线批量推理性能
- **Specialized benchmarks**：结构化输出、前缀缓存、长文档 QA、请求优先级、多模态等
- **Dataset utilities**：统一的数据集加载/采样框架（ShareGPT、HuggingFace、合成数据等）

### 3.2 三个核心子命令

| 子命令 | 定位 | 运行方式 | 典型输出 |
|--------|------|---------|---------|
| `vllm bench throughput` | 离线吞吐（offline） | 本地起 LLM 引擎，一次性送 N 条 prompt | `requests/s`、`tokens/s` |
| `vllm bench serve` | 在线 serving（最常用） | 向已启动的 OpenAI-compatible server 发流量 | TTFT、TPOT、ITL、E2E latency、req/s、token/s、可选 goodput |

三者共享同一套引擎参数（ModelConfig / CacheConfig / SchedulerConfig / ParallelConfig），但请求生成逻辑不同。

### 3.3 关键能力（按维度归类）

**流量形状控制**

`vllm bench serve` 通过以下参数控制到达过程：
- `--request-rate`：目标请求速率（默认 `inf` = 一次全下发）
- `--burstiness`：Gamma 分布控制突发性（`1.0` = 自然 Poisson，`<1.0` = 更突发，`>1.0` = 更均匀）
- `--max-concurrency`：并发上限，模拟网关/负载均衡器约束
- `--ramp-up-strategy` + `--ramp-up-start-rps` / `--ramp-up-end-rps`：线性/指数爬坡

**最大吞吐模式**（`--request-rate=inf --max-concurrency=<limit>`）是生产评测最常见配置。

**数据集支持**

| 数据集 | 类型 | 来源 |
|--------|------|------|
| `random` / `random-mm` | 合成 | 给定 input/output-len，完全可控可复现 |
| `sharegpt` | 真实对话 | JSON 文件，接近真实分布 |
| `prefix_repetition` | 合成 | 专门评测 prefix caching |
| `hf` | 通用 | 任意 HuggingFace 数据集 |
| `custom` | 本地 | `.jsonl` 含 `"prompt"` 字段 |
| `spec_bench` / `speed_bench` | 学术 | 投机解码评测 |
| `burstgpt` | Trace | CSV 格式 |

**指标与分位数**

- `--percentile-metrics ttft,tpot,itl,e2el`：选择要输出分位数的指标
- `--metric-percentiles 50,90,99`：选择百分位点
- 生成式模型默认输出 `ttft,tpot,itl`；pooling 模型默认 `e2el`

**Goodput（SLO 视角）**

```bash
--goodput ttft:200 tpot:50 e2el:3000
```

定义来自 DistServe（arXiv 2401.09670），计算"同时满足给定 SLO 的那部分吞吐"，对判断"加并发后到底有多少吞吐是合格的"非常关键。

**结果落盘**

- `--save-result`：保存汇总 JSON
- `--save-detailed`：保存每条请求的独立指标（`.jsonl`），便于绘制分布图
- `--result-dir` / `--result-filename` / `--metadata`：组织输出
- `--plot-timeline` / `--plot-dataset-stats`：直接出图
- `--num-warmups`：预热请求数，避开冷启动、CUDA graph 首次捕获等噪声
- `--ready-check-timeout-sec`：自动等待 server 就绪

### 3.4 指标定义与对应口径

| 指标 | 全称 | vLLM 内的口径 |
|------|------|-------------|
| **TTFT** | Time To First Token | 请求发出到收到第一个 token 的墙钟时间 |
| **TPOT** | Time Per Output Token | 除首个 token 外，每个输出 token 的平均生成时间 |
| **ITL** | Inter-Token Latency | token 之间的间隔分布（P50/P90/P99） |
| **E2E Latency** | End-to-End Latency | 整个请求完成耗时 |
| **Request Throughput** | — | req/s |
| **Input/Output/Total Token Throughput** | — | tok/s，分上下行分别统计 |
| **Goodput** | Good Throughput | 满足 `--goodput` SLO 约束的有效吞吐 |

### 3.5 优势与局限

**优势**
- 官方同源，与 vLLM 新特性同步快
- 数据集覆盖广，含多模态与 speculative decoding 场景
- 快速构建单机/单服务基线，适合迭代调参
- 与 KVFabric `evaluation-plan.md` Phase 1 metrics 精确对齐

**局限**
- 官方文档明确其主目标是特性评估与回归，不是完整生产评估框架
- 仅测 vLLM 自身，跨引擎对比能力为 0
- 无内置 GPU 资源采样（GPU util、HBM 占用、KV cache usage），需从 `log-stats` 或 `nvidia-smi` 获取
- 对跨引擎可比性、SLO 分析链路、报告体系的"平台化能力"不如 inference-perf

### 3.6 核心命令模板

```bash
# === 离线吞吐基线 ===
vllm bench throughput \
  --model Qwen/Qwen3.5-2B \
  --dataset-name random \
  --random-input-len 512 \
  --random-output-len 128 \
  --num-prompts 100

# === 在线 Serving — 最大吞吐 ===
vllm bench serve \
  --backend vllm \
  --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 512 \
  --random-output-len 128 \
  --num-prompts 200 \
  --save-result --save-detailed \
  --result-dir results/max_tp

# === 在线 Serving — 固定 QPS + Poisson 到达 ===
vllm bench serve \
  --backend vllm \
  --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 \
  --request-rate 10 --burstiness 1.0 \
  --save-result --result-dir results/qps10

# === 在线 Serving — 爬坡压测（找饱和点） ===
vllm bench serve \
  --backend vllm \
  --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 512 --random-output-len 128 \
  --num-prompts 500 \
  --ramp-up-strategy linear \
  --ramp-up-start-rps 1 --ramp-up-end-rps 50

# === 在线 Serving — Goodput ===
vllm bench serve \
  --backend vllm \
  --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --request-rate inf \
  --goodput ttft:200 tpot:50 e2el:3000 \
  --save-result --result-dir results/goodput

# === Prefix Cache A/B ===
# Server 端: 加/去 --enable-prefix-caching
vllm serve Qwen/Qwen3.5-2B --enable-prefix-caching --port 8000 &

vllm bench serve \
  --backend vllm --model Qwen/Qwen3.5-2B \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 1024 --random-output-len 128 \
  --random-prefix-len 512 \
  --num-prompts 100 \
  --save-result --result-dir results/prefix_on

# === 输入/输出长度扫描 ===
for input_len in 128 512 1024 2048; do
  for output_len in 64 128 256; do
    vllm bench serve \
      --backend vllm --model Qwen/Qwen3.5-2B \
      --endpoint /v1/completions \
      --dataset-name random \
      --random-input-len $input_len \
      --random-output-len $output_len \
      --num-prompts 100 \
      --save-result --result-dir results/scan_i${input_len}_o${output_len}
  done
done
```

---

## 4. inference-perf 深度分析

### 4.1 工具定位

`kubernetes-sigs/inference-perf` 自定位为"production-scale GenAI inference performance benchmarking tool"，核心差异在于：

- **model server agnostic**：同一套压测框架横向对比不同引擎（已验证支持 vLLM、SGLang、TGI）
- 源于 Kubernetes `wg-serving` 的 inference benchmarking and metrics standardization 努力
- 用相同负载评估不同服务端是"apples-to-apples"对比

### 4.2 核心能力

**Rich Metrics & Analysis**
- Latency：TTFT / TPOT / ITL / Normalized TPOT
- Throughput：input / output / total tokens per second
- Goodput：满足 SLO 的请求率，定义和口径在 `docs/goodput.md` 统一
- 自动画图：QPS vs Latency / Throughput / Goodput
- 统一 report schema（`docs/reports.md` 定义 JSON schema），适合入库和跨引擎对比

**Smart Data Generation**
- 真实数据集：ShareGPT、CNN DailyMail、Infinity Instruct、Billsum
- 合成/随机：按指定分布采样 input/output length
- 进阶场景：shared prefix、multi-turn chat conversations
- Trace Replay：Azure LLM inference trace 或 OpenTelemetry traces，支持 agentic tree-of-thought

**Flexible Load Generation**
- 负载形状：constant rate、Poisson arrival、concurrent user simulation
- Multi-stage runs：单次 benchmark 定义多段 `{rate, duration}`，自动找饱和点
- Trace Replay：回放真实 trace

**High Scalability**
- 单实例声称 10k+ QPS，支持 automatic saturation detection
- 多进程 + 多线程架构

**Engine Agnostic**
- 只要 OpenAI-compatible endpoint 就能接
- MultiLoRA：traffic split 与 per-adapter 独立报告

### 4.3 指标体系

与 vLLM bench 核心指标一一对应（TTFT/TPOT/ITL/throughput/goodput），但有两处关键差别：

| 差别 | 说明 |
|------|------|
| **Normalized TPOT** | 对不同 output_len 做归一化，方便跨 workload 比较 |
| **价格性能指标** | $/M tokens、Throughput/$，对容量规划有直接意义 |

### 4.4 Goodput 与 SLO 能力

`docs/goodput.md` 定义"满足约束的有效吞吐"，支持：
- 全局阈值（ttft / tpot / itl / ntpot / request_latency）
- 按请求头覆盖阈值
- 输出 Request Goodput、Token Goodput、Goodput%

能回答的核心问题："系统跑得快，但是否达标"。

### 4.5 运行形态

三种官方支持方式：

```bash
# 方式 1: 本地 pip
pip install inference-perf
inference-perf --server.type vllm --server.base_url http://localhost:8000 \
  --data.type random --load.type constant \
  --load.stages '[{"rate": 10, "duration": 60}]' --api.streaming true

# 方式 2: Docker
docker run -it --rm -v $(pwd)/config.yml:/workspace/config.yml \
  quay.io/inference-perf/inference-perf

# 方式 3: Kubernetes（Helm chart 在 deploy/ 目录）
```

### 4.6 配置文件示例

```yaml
# config_kvbench.yaml
server:
  type: vllm
  base_url: http://localhost:8000
  model: Qwen/Qwen3.5-2B

data:
  type: random
  random:
    input_len: 512
    output_len: 128
    num_prompts: 200

load:
  type: constant
  stages:
    - rate: 5
      duration: 60
    - rate: 10
      duration: 60
    - rate: 20
      duration: 60

api:
  streaming: true

goodput:
  ttft: 200
  tpot: 50
  itl: 100

output:
  dir: results/inference_perf
```

```bash
inference-perf --config_file config_kvbench.yaml
```

### 4.7 Shared Prefix 场景（KVFabric 复用评测关键）

```yaml
# config_shared_prefix.yaml
server:
  type: vllm
  base_url: http://localhost:8000
  model: Qwen/Qwen3.5-2B

data:
  type: shared_prefix
  shared_prefix:
    prefix_len: 512
    suffix_len: 256
    num_prefixes: 5
    requests_per_prefix: 20

load:
  type: constant
  stages:
    - rate: 10
      duration: 120
```

### 4.8 优势与局限

**优势**
- 跨引擎公平对比能力强（同一负载压在 vLLM / SGLang / TGI 上）
- SLO/Goodput 语义完整，适合生产容量规划
- 报告与可视化链路体系化
- shared prefix / conversation replay 场景可直接为 KVFabric 任务 2 提供数据生成器
- Trace Replay 为将来把 KVFabric 放到真实生产 trace 上评测预留入口

**局限**
- 接入与配置复杂度高于 vLLM bench
- 对 vLLM 特有功能的细节回归，不如官方 bench 直接
- 不暴露引擎内部指标（GPU KV cache usage、block pool、Running/Waiting 队列）
- 单机使用相比 vLLM bench 启动开销偏大，lightweight smoke test 不如前者
- Engine agnostic 的代价：要拿 vLLM 特定能力（如 prefix caching 的 A/B）还是得回到 vLLM bench

---

## 5. Vidur 深度分析

### 5.1 工具定位

Vidur（MLSys'24）是高保真 LLM 推理仿真框架，**不是压测客户端**。核心理念：不跑真实 GPU，而通过"算子级实验 profiling + 预测建模"估计端到端延迟/吞吐。

官方定位三件事：
1. 研究不同 workload / 配置下的系统性能
2. 容量规划（capacity planning），为部署找最优配置
3. 快速评估新研究想法（新调度算法、投机解码等），除一次性 profiling 外不需要 GPU

### 5.2 核心技术方案

- **Operator-Level Profiling**：对 attention、MLP 等各算子进行一次性真实 GPU profiling
- **Predictive Modeling**：用 Random Forest + Linear Regression 组合预测各算子在不同配置下的执行时间
- **End-to-End Simulation**：模拟完整推理 pipeline — 请求到达、调度、批处理、执行、资源利用
- **Extensible Design**：可插入新调度算法、新模型、新硬件 SKU、speculative decoding 等

### 5.3 量化价值

论文直接给出的数字：
- 延迟估计误差 **< 9%**（部分场景 < 5%）
- Vidur-Search 在 CPU 上**约 1 小时**找到 LLaMA2-70B 最优配置
- 若用部署实测搜索，约需 **42K GPU 小时**，成本约 **$218K**

核心价值：**把高成本实测搜索前移为低成本仿真搜索**。

### 5.4 覆盖能力

**模型 / 硬件矩阵**

| 模型 | A100 80GB DGX | H100 DGX | 4xA100 NVLink | 8xA40 NVLink |
|------|:---:|:---:|:---:|:---:|
| Llama-3-8B | Y | - | Y | - |
| Llama-3-70B | Y | - | Y | - |
| Llama-2-7B | Y | Y | Y | Y |
| CodeLlama-34B | Y | Y | Y | Y |
| Llama-2-70B | Y | Y | Y | Y |
| InternLM-20B | Y | Y | Y | Y |
| Qwen-72B | Y | Y | Y | Y |

- 支持 TP（1/2/4/8，DGX NVLink） + PP 任意组合
- 默认 max 4K context；Llama3 系列可通过配置扩展至 16K

**调度器与配置**

- 内置 `sarathi` 调度器
- 可配置 `batch_size_cap`、`chunk_size`
- 支持 Poisson 等请求到达分布
- 输入：synthetic request generator + 真实 trace 文件（如 `splitwise_conv.csv`）

**输出能力**

- metrics：TTFT / TPOT / Request E2E Time / Batch Size，通过 wandb 和本地双份落盘
- Chrome Tracing 兼容 trace：`chrome://tracing/` 直接打开，能看到调度/批次时间线
- canary 分支迭代中：prefix caching、新 routing policy、simulator 内存优化等

### 5.5 典型运行命令

```bash
python -m vidur.main \
  --replica_config_device a100 \
  --replica_config_model_name meta-llama/Meta-Llama-3-8B \
  --cluster_config_num_replicas 1 \
  --replica_config_tensor_parallel_size 1 \
  --replica_config_num_pipeline_stages 1 \
  --request_generator_config_type synthetic \
  --synthetic_request_generator_config_num_requests 512 \
  --length_generator_config_type trace \
  --trace_request_length_generator_config_trace_file ./data/processed_traces/splitwise_conv.csv \
  --interval_generator_config_type poisson \
  --poisson_request_interval_generator_config_qps 6.45 \
  --replica_scheduler_config_type sarathi \
  --sarathi_scheduler_config_batch_size_cap 512 \
  --sarathi_scheduler_config_chunk_size 512
```

等价于：不占 GPU，也能告诉你 A100 + Llama3-8B + Sarathi 调度 + QPS 6.45 下的 TTFT/TPOT/batch size。

### 5.6 Vidur 角色定位（在评测体系中的位置）

**适合的问题**
- 不同并行维度（TP/PP/副本数）如何影响性能和成本
- 不同调度策略、批处理参数、流量特征下的最优点
- 新模型或新流量进入时，先快速缩小实验空间
- 回答"不改代码、不占 GPU，换一种调度/并行策略会变好吗"

**不适合单独承担的问题**
- 线上真实链路抖动、网络噪声、驱动细节、实现缺陷
- 最终发布前的真实性能签收
- KV Cache 物理布局改动的评测
- 代码级实现的正确性验证

**方法论指导意义**
- 论文的 `experimental profiling + predictive modeling` 路径给 KVFabric 未来评估"假设我们改了驱逐/复用策略"提供了一条不需要真机复现的研究路径
- Chrome trace 可视化能帮助把宏观指标（TTFT/TPOT）和 scheduler 行为（batch 演化、请求在队列里等多久）对应起来，解释瓶颈类别

### 5.7 KVFabric What-If 参数对照

| KVFabric 探索问题 | Vidur 参数调整 |
|------------------|---------------|
| 增大 batch size 上限对 TTFT/吞吐的影响 | `--sarathi_scheduler_config_batch_size_cap 128/256/512` |
| prefilling 分块大小对首 token 延迟的影响 | `--sarathi_scheduler_config_chunk_size 128/256/512` |
| 不同 QPS 下的排队延迟占比 | `--poisson_request_interval_generator_config_qps 3/6/12` |
| 长序列占比增加后的系统行为 | 替换 trace 文件为长尾分布的长度数据 |

### 5.8 对 KVFabric 的注意点

- Vidur 内置模型库未直接包含 `Qwen3.5-2B`，需自行 profiling 或使用同量级模型（如 Llama-3-8B）替代分析
- batch 演化、TTFT 构成比例等**定性结论**可迁移；**绝对性能数字**不可迁移
- 模拟的是 Sarathi 风格调度，对标 vLLM continuous batching 需理解抽象口径差异
- 主分支停在 Llama3 一线；prefix caching 等新特性在 canary 分支，稳定性需自行验证

---

## 6. 三工具分工与推荐流水线

### 6.1 为什么三工具比单一工具更稳

| 只用... | 风险 |
|---------|------|
| vLLM bench | 快，但生产语义不完整 |
| inference-perf | 全面，但调试回归效率偏低 |
| Vidur | 搜索快，但缺少真实系统噪声 |

三者组合覆盖：**回归速度 + 生产真实性 + 搜索成本**。

### 6.2 推荐三层流水线

```
第 1 层: vLLM bench     →  快速基线 + 参数回归
              ↓
第 2 层: inference-perf  →  生产负载 + SLO 验证 + 跨引擎对照
              ↓
第 3 层: Vidur           →  瓶颈解释 + what-if 配置搜索
```

### 6.3 各层具体分工

| 工具 | 角色 | 什么时候用 | 需要产出 |
|------|------|----------|---------|
| `vllm bench` | **主评测工具** | 所有正式数据点（input/output len × 并发 × prefix on/off） | `summary.csv`、每组 JSON 原始结果 |
| `inference-perf` | **Sanity check + 高阶负载** | 在一组典型配置上对拍；为任务 2 准备 shared prefix / conversation replay 数据 | 1-2 组对拍结果，确认口径一致 |
| Vidur | **瓶颈解释 + what-if** | vLLM bench 结果出来后，回放同量级 workload 分析 bottleneck | chrome trace 截图 + 瓶颈判定 |

### 6.4 如何回答三个核心问题

| 问题 | 回答路径 |
|------|---------|
| ① vLLM 在普通 serving 场景下性能是多少 | 主要由 `vllm bench serve/throughput` 得出 |
| ② 系统瓶颈在 prefill/decode/调度/显存 | `vllm bench` 指标 + `nvidia-smi` 采样 + Vidur 时间线交叉解释 |
| ③ 后续 KVCache 优化应优先降 TTFT 还是提吞吐 | prefix on/off 的 A/B 在 `vllm bench` 上给出第一版答案，用 `inference-perf` 的 shared prefix 再验证 |

---

## 7. KVFabric 实战指南

### 7.1 Phase 1 & 2 评测流水线图

```
┌──────────────────────────────────────────────────────┐
│ Phase 1: Official vLLM Baseline                      │
│                                                      │
│  ① vllm bench throughput  → 离线吞吐基线              │
│  ② vllm bench serve       → 在线延迟基线              │
│     ├─ 扫描 input/output len                         │
│     ├─ 扫描并发度 / QPS                               │
│     └─ prefix cache A/B                              │
│  ③ Vidur                 → 瓶颈时间线分析              │
│                                                      │
│  产出: baseline_result.csv + chrome trace 截图        │
├──────────────────────────────────────────────────────┤
│ Phase 2: vLLM Python Prototype vs Baseline           │
│                                                      │
│  ④ vllm bench serve       → 改造后回归测试            │
│  ⑤ inference-perf         → 生产负载 + SLO 验证       │
│     ├─ sharegpt 真实分布                              │
│     ├─ shared_prefix 复用场景                         │
│     └─ sweep 找吞吐拐点                               │
│  ⑥ Vidur                 → 新调度策略 what-if         │
│                                                      │
│  产出: goodput 曲线 + SLO 达标报告 + 对比表            │
└──────────────────────────────────────────────────────┘
```

### 7.2 一次完整评测的推荐执行脚本

```bash
#!/bin/bash
# KVFabric Phase 1 完整评测脚本
set -e

MODEL="Qwen/Qwen3.5-2B"
RESULT_BASE="results/phase1"

# 1. 环境检查
echo "=== 环境检查 ==="
python -c "import vllm; print('vLLM', vllm.__version__)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# 2. 启动 vLLM 服务 (prefix caching ON)
echo "=== 启动 vLLM Server ==="
vllm serve $MODEL \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.9 \
  --max-model-len 4096 \
  --port 8000 &
SERVER_PID=$!
sleep 30  # 等 server 就绪

# 3. 最大吞吐基准
echo "=== 最大吞吐基准 ==="
vllm bench serve --backend vllm --model $MODEL \
  --endpoint /v1/completions \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --save-result --save-detailed \
  --result-dir $RESULT_BASE/max_tp

# 4. Poisson QPS 扫描
echo "=== QPS 扫描 ==="
for qps in 5 10 15 20; do
  vllm bench serve --backend vllm --model $MODEL \
    --endpoint /v1/completions \
    --dataset-name random --random-input-len 512 --random-output-len 128 \
    --num-prompts 200 --request-rate $qps --burstiness 1.0 \
    --save-result --result-dir $RESULT_BASE/qps_${qps}
done

# 5. 长度扫描矩阵
echo "=== 长度扫描 ==="
for input_len in 128 512 1024 2048; do
  for output_len in 64 128 256; do
    vllm bench serve --backend vllm --model $MODEL \
      --endpoint /v1/completions \
      --dataset-name random \
      --random-input-len $input_len --random-output-len $output_len \
      --num-prompts 100 --save-result \
      --result-dir $RESULT_BASE/scan_i${input_len}_o${output_len}
  done
done

# 6. 停 server，关 prefix caching 重跑对比
kill $SERVER_PID
sleep 5

echo "=== Prefix Cache OFF 对比 ==="
vllm serve $MODEL \
  --gpu-memory-utilization 0.9 \
  --max-model-len 4096 \
  --port 8000 &
SERVER_PID=$!
sleep 30

vllm bench serve --backend vllm --model $MODEL \
  --endpoint /v1/completions \
  --dataset-name random \
  --random-input-len 1024 --random-output-len 128 --random-prefix-len 512 \
  --num-prompts 100 --save-result \
  --result-dir $RESULT_BASE/prefix_off

# 7. 清理
kill $SERVER_PID
echo "=== Phase 1 评测完成 ==="
```

### 7.3 与 vLLM bench 的对拍验证

```bash
# 同模型、同负载、两个工具对比
# vLLM bench
vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 200 --request-rate inf --save-result --result-dir results/vllmbench_ref

# inference-perf
inference-perf --server.type vllm --server.base_url http://localhost:8000 \
  --data.type random --load.type constant \
  --load.stages '[{"rate": 1000, "duration": 60}]' \
  --api.streaming true --output.dir results/inferenceperf_ref
```

> 两者 tok/s 差异应在 10-15% 以内。差异主要来自：客户端实现细节、tokenizer 计数方式、首个 token 统计口径。

### 7.4 报告建议的标注方式

若输出"标准基础服务性能测试"章节，建议明确标注：

- 基线值来自 **vLLM bench**
- 生产结论来自 **inference-perf**（含 goodput 约束）
- 配置选择依据 **Vidur** 的候选区间再实测确认

这样报告从"单次跑分"升级为"可迁移的评测方法学"。

---

## 8. 附录

### 8.1 命令速查表

| 场景 | 命令 |
|------|------|
| 离线吞吐 (random) | `vllm bench throughput --model Qwen/Qwen3.5-2B --dataset-name random --random-input-len 512 --random-output-len 128 --num-prompts 100` |
| 在线最大吞吐 | `vllm bench serve --backend vllm --model Qwen/Qwen3.5-2B --dataset-name random --random-input-len 512 --random-output-len 128 --num-prompts 200 --request-rate inf` |
| 在线固定 QPS | 加 `--request-rate 10 --burstiness 1.0` |
| 在线爬坡 | 加 `--ramp-up-strategy linear --ramp-up-start-rps 1 --ramp-up-end-rps 50` |
| 在线 Goodput | 加 `--goodput ttft:200 tpot:50 e2el:3000` |
| Prefix cache A/B | Server 加/去 `--enable-prefix-caching`，client 用 `--random-prefix-len 512` |
| inference-perf 最小 | `inference-perf --server.type vllm --server.base_url http://localhost:8000 --data.type random --load.type constant --load.stages '[{"rate":10,"duration":60}]'` |
| Vidur 仿真 | `python -m vidur.main --replica_config_device a100 --replica_config_model_name ... --request_generator_config_type synthetic ...` |

### 8.2 指标定义速查表

| 指标 | 全称 | 含义 | vLLM | inf-perf | Vidur |
|------|------|------|:---:|:---:|:---:|
| **TTFT** | Time To First Token | 请求发出到收到第一个 token 的时间 | Y | Y | Y |
| **TPOT** | Time Per Output Token | 除首个 token 外每个输出 token 的平均生成时间 | Y | Y | Y |
| **ITL** | Inter-Token Latency | 相邻 token 之间的间隔分布 | Y | Y | - |
| **E2E Latency** | End-to-End Latency | 整个请求的墙钟完成时间 | Y | Y | Y |
| **NTPOT** | Normalized TPOT | 对 output_len 归一化的 TPOT | - | Y | - |
| **Goodput** | Good Throughput | 满足 SLO 约束的有效吞吐 | Y | Y | - |
| **Request Throughput** | — | 每秒完成请求数 (req/s) | Y | Y | Y |
| **Token Throughput** | — | 每秒生成 token 数 (tok/s) | Y | Y | Y |

### 8.3 参考链接

| 资源 | 链接 |
|------|------|
| vLLM Benchmark CLI 文档 | https://docs.vllm.ai/en/stable/benchmarking/cli/ |
| vLLM Benchmark 源码 | https://github.com/vllm-project/vllm/tree/main/benchmarks |
| inference-perf GitHub | https://github.com/kubernetes-sigs/inference-perf |
| Vidur GitHub | https://github.com/microsoft/vidur |
| Vidur 论文 (arXiv) | https://arxiv.org/abs/2405.05465 |
| GuideLLM（生产评估推荐） | https://github.com/vllm-project/guidellm |
| KVFabric 评测计划 | ../../../evaluation-plan.md |
