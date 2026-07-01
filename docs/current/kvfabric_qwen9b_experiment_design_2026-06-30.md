# KVFabric Qwen3.5-9B 实验设计说明

本文详细说明 KVFabric 面向 Qwen3.5-9B 设计的实验体系，包括小实验、中等实验、完整长实验，以及每类实验的模拟场景、请求组成、请求发送方式和验证目标。本文重点写清楚“到底发了什么请求、怎么发、为什么这样发”，方便直接转化为期末汇报 PPT 素材。

## 1. 实验平台与统一口径

### 1.1 模型与服务配置

9B 实验使用远程 2 x RTX 3090 服务器运行 vLLM OpenAI server。

模型 profile 的核心参数为：

| 项目 | 配置 |
| --- | --- |
| 模型 | `Qwen/Qwen3.5-9B` |
| served model name | `qwen3.5-9b-local` |
| tensor parallel | `2` |
| max model length | `4096` |
| max num seqs | `64` |
| max num batched tokens | `24576` |
| prefix caching | enabled |

容量设置分为三档：

| 容量档位 | `GPU_MEMORY_UTILIZATION` | 用途 |
| --- | ---: | --- |
| small | `0.55` | 制造更强 KV cache 压力，用于容量敏感性或快速放大问题 |
| medium | `0.70` | 最终主实验默认容量，更接近普通服务部署 |
| large | `0.85` | 用于低复用非回归，避免把容量压力误当作策略收益 |

### 1.2 对比策略

所有实验都以 vLLM 原始 LRU 风格策略作为 baseline，再和 KVFabric profile 对比。

| 策略 | 含义 | 主要验证点 |
| --- | --- | --- |
| `lru` | 关闭 KVFabric 控制策略，保留 vLLM prefix cache / BlockPool 基础行为 | baseline |
| `kvfabric_admission` | 重点打开 hint-aware admission | 低价值请求少占 cache，高价值请求保留空间 |
| `kvfabric_throughput` | admission 为主，轻量 eviction 保护，scheduler 关闭 | 高压共享前缀场景下提升 SLO goodput |
| `kvfabric_rebuilt` | 更强调 rebuilt-from-eviction 反馈和 family-aware eviction | 减少错误驱逐后的重建 |
| `kvfabric_latency` | 关闭 admission/eviction，打开 scheduler latency protection | 前台交互请求延迟保护 |

最终主矩阵里只保留四个 stage：`prefill_throughput_medium`、`interactive_latency_medium`、`enterprise_normal_medium`、`low_reuse`。其他小实验和中等实验主要用于调参、定位问题和证明机制。

## 2. 请求是怎么发送到 vLLM 的

9B 实验通过 vLLM 的 OpenAI-compatible server 真实发送请求，离线脚本只负责生成 trace、payload 和后处理 summary。

### 2.1 请求接口

load generator 向服务端发送：

```text
POST /v1/chat/completions
```

每个请求包含：

```json
{
  "model": "qwen3.5-9b-local",
  "messages": [
    {"role": "system", "content": "...长系统提示词..."},
    {"role": "user", "content": "...用户问题..."}
  ],
  "temperature": 0.0,
  "max_tokens": 64
}
```

多轮对话请求会携带更长的 `messages` 历史，例如：

```json
{
  "messages": [
    {"role": "system", "content": "企业共享策略、租户规则、工作流模板..."},
    {"role": "user", "content": "第 1 轮问题..."},
    {"role": "assistant", "content": "第 1 轮模拟回答..."},
    {"role": "user", "content": "第 2 轮追问..."}
  ]
}
```

这样后续 turn 会天然复用前面 turn 的长前缀，能够模拟真实多轮会话中的 KV prefix reuse。

### 2.2 KVFabric hint headers

请求还会带 `x-kvfabric-*` headers。它们不改变模型语义，只给 KVFabric 控制面提供资源管理提示。

常见 headers 包括：

| Header | 含义 |
| --- | --- |
| `x-kvfabric-request-class` | 请求类别，例如 `durable_hot_family`、`cold_rag_unique`、`short_chat_qa` |
| `x-kvfabric-cache-priority` | cache 优先级，例如 `high`、`normal`、`low`、`bypass` |
| `x-kvfabric-expected-reuse` | 预期复用，例如 `durable`、`transient`、`none`、`unknown` |
| `x-kvfabric-tenant-id` | 租户 ID |
| `x-kvfabric-family-id` | 前缀 family ID |
| `x-kvfabric-session-id` | 会话 ID |
| `x-kvfabric-turn-index` | 多轮对话轮次 |
| `x-kvfabric-phase` | 所属阶段，例如 `warmup`、`main`、`revisit`、`red_burst` |
| `x-kvfabric-slo-ms` | 请求 SLO，单位毫秒 |
| `x-kvfabric-hint-confidence` | hint 置信度 |

vLLM serving 层读取这些 headers 后，写入 `RequestMeta`，后续 admission、eviction、scheduler 都只读取这个控制面元数据，不改模型输出。

### 2.3 两种 load generator

9B 实验使用两类负载生成器。

第一类是 duration loadgen，适合构造“固定请求池 + 分阶段并发”的压力实验：

- 先根据配置生成一批 payload。
- 每个 worker 循环从 payload pool 中取请求。
- 按 segment 控制持续时间、并发、是否计分、包含哪些 request class。
- 每个请求立刻通过 OpenAI 接口发送。
- 记录 latency、e2e latency、SLO goodput、class metrics、segment metrics。

对应脚本是 `online_duration_loadgen.py` 和 `online_batch.py`。

第二类是 trace loadgen，适合模拟“真实时间线”的企业混合流量：

- 先用 trace generator 生成 `trace.jsonl`。
- 每条 trace 里有计划发送时间 `scheduled_at_seconds`、request class、tenant、family、session、prompt 文件路径等。
- replay 时按照 trace 时间睡眠，到点发送请求。
- 用 semaphore 控制最大 in-flight 请求数。
- 记录 send delay、service latency、e2e latency、SLO goodput 和 class metrics。

对应脚本是 `generate_realistic_trace.py` 和 `online_trace_loadgen.py`。

### 2.4 指标口径

核心指标分为四类：

| 指标 | 含义 |
| --- | --- |
| throughput | 完成请求数、req/s、tokens/s |
| latency | service p50/p95/p99，e2e p50/p95/p99 |
| SLO goodput | 在指定 SLO 内完成的有效吞吐 |
| KV lifecycle | prefix hit ratio、eligible hit ratio、warm-family hit ratio、evicted blocks、rebuilt-from-eviction、admission limited blocks |

其中 e2e latency 包括排队等待、send delay 和服务端处理时间，更适合展示 scheduler latency protection；service latency 更接近请求进入服务端后的实际完成时间。

## 3. 请求内容是怎么构造的

### 3.1 共享前缀的来源

所有 9B workload 都通过“重复文本片段 + 租户模板 + family 模板 + 会话历史”制造可控的 prefix reuse。

典型共享前缀由几层组成：

1. 全局共享系统提示词：所有请求都可能包含的企业网关规则、安全策略、回答格式。
2. 租户级提示词：同一 tenant 的请求共享，例如租户业务规则、字段解释。
3. 工作流或 family 提示词：同一 family 的请求共享，例如同一 RAG 文档、同一代码仓库说明、同一客服流程。
4. 会话历史：同一 session 的多轮对话共享前面 turn 的 messages。

KVFabric 的保护对象是这些在真实服务中会反复出现的前缀主干。

### 3.2 duration workload 的请求类型

`saturation_throughput_pressure` 是 9B 吞吐主线最重要的 workload。它每一轮生成多类请求：

| 请求类 | 典型含义 | cache hint | max_tokens | 作用 |
| --- | --- | --- | ---: | --- |
| `durable_hot_family` | 稳定热门业务模板或热门 RAG family | high / durable | 64 | 形成应被长期保留的共享前缀 |
| `sticky_session_followup` | 多轮会话后续追问 | high / durable | 48 或 64 | 模拟聊天/客服/代码助手里的会话前缀复用 |
| `cold_rag_unique` | 一次性冷 RAG 查询 | low / none | 64 | 制造冷流量，占用 KV cache |
| `cold_rag_burst` | 突发冷 RAG 查询 | bypass 或 low / none | 64 | 制造短时 cache churn 和容量压力 |
| `transient_template_family` | 短生命周期模板 family | normal / transient | 64 | 检验 transient 请求是否应该少缓存 |
| `decode_heavy` | 长输出生成请求 | low / none | 320 | 模拟低复用但长 decode 的后台任务 |

这些请求的 prompt 都是有意构造的：

- `durable_hot_family` 会反复使用同一个 tenant prefix 和 family prefix。
- `sticky_session_followup` 会反复带上同一个 session 的历史消息。
- `cold_rag_unique` 每次使用不同 family，几乎不复用。
- `cold_rag_burst` 在某些 round 集中出现，模拟突然涌入的冷检索请求。
- `decode_heavy` 的 prompt 不一定很长，但输出 token 多，会占用计算和队列资源。

### 3.3 trace workload 的请求类型

trace workload 更像真实企业网关流量。它由 `generate_realistic_trace.py` 按时间生成请求。

主要 profile 包括：

| Profile | 模拟场景 |
| --- | --- |
| `enterprise_mixed` | 企业多租户混合流量，既有热 workflow，也有冷查询和多轮会话 |
| `daily_dedicated_reuse` | 日常高复用流量，部分租户和 family 反复出现 |
| `sticky_burst` | 会话粘性较强，并伴随 burst |
| `low_reuse_low_frequency` | 低频低复用流量，多数请求没有再次使用价值 |
| `conversation_sticky` | 多轮会话占比较高 |
| `general_gateway` | 普通网关混合请求 |

trace 里的 session 请求会随着时间继续增长历史：

- 第一次请求创建 session，带 system prompt 和第一个 user turn。
- 后续请求复用同一个 session id，把之前的 user/assistant 历史一起发出。
- 每一轮都增加 `turn_index`，并带上 `phase`、SLO 和 hint headers。

这使得 trace workload 能模拟“真实聊天历史越来越长、前缀越来越值得复用”的情况。

## 4. 小实验：快速 smoke、容量和基础 profile 校准

### 4.1 `qwen3_5_9b_capacity_sweep_6m.json`

这是 6 分钟容量敏感性小实验。

配置要点：

- trace profile：`daily_dedicated_reuse`
- duration：360s
- target rate：0.5 req/s
- max in flight：32
- warmup：45s
- hint regime：partial hints
- session reuse probability：0.88
- SLO：60s

请求组成：

- 大量 session followup 请求，模拟同一批用户在一天内反复追问。
- 部分 hot family 请求，模拟租户工作流复用。
- 少量 cold request，用来制造轻微 cache churn。

验证目标：

- small / medium / large 容量下，LRU 与 KVFabric 的差异是否随容量变化。
- 判断 9B 的默认实验容量应该选在哪里。
- 快速发现某个容量档是否过于极端。

结论口径：

- 该实验用于帮助确定 medium capacity 作为主实验默认值，不作为最终主结果。

### 4.2 `qwen3_5_9b_quick_daily_8m.json`

这是 8 分钟日常复用 quick test。

配置要点：

- trace profile：`daily_dedicated_reuse`
- duration：480s
- target rate：0.45 req/s
- max in flight：40
- session reuse probability：0.86
- SLO：90s

请求组成：

- 多轮 session 请求占比较高。
- family 复用明显，但压力不极端。
- 冷流量存在，但不会像 final throughput stage 那样强烈冲击 cache。

验证目标：

- 检查 9B 服务、headers、trace replay、summary 链路是否正常。
- 验证 KVFabric 在普通日常复用场景下不会明显退化。

## 5. 中等实验：吞吐策略探索

### 5.1 `qwen3_5_9b_prefill_reuse_quick_12m.json`

这是 12 分钟 prefill reuse 快速实验，用来早期寻找 9B 是否存在可利用的 prefix reuse。

配置要点：

- workload：`saturation_throughput_pressure`
- rounds：1200
- tenants：4
- hot families：10
- sticky sessions：48
- hot family per round：22
- sticky followup per round：10
- cold RAG per round：3
- transient per round：1
- burst every 10 rounds，burst cold requests：4
- decode every 10 rounds
- concurrency：80
- request selection：shuffle
- SLO probes：14s、16s、18s、20s、22s、25s、30s

请求发送分三个 segment：

| Segment | 时长 | 并发 | 是否计分 | 作用 |
| --- | ---: | ---: | --- | --- |
| `warmup` | 120s | 32 | 否 | 建立热 family 和 sticky session 工作集 |
| `prefill_main` | 480s | 80 | 是 | 高并发复用主阶段 |
| `cold_churn_burst` | 120s | 88 | 是 | 插入冷流量冲击，观察 cache 是否被污染 |

验证目标：

- 9B 是否能在明显复用场景下产生 prefix hit 差异。
- admission 和 family protect 是否有潜在收益。
- 找到后续 60 分钟版本的并发和 SLO 范围。

### 5.2 `qwen3_5_9b_prefill_reuse_saturation_60m.json`

这是 60 分钟中等长度吞吐实验，是 quick 版本的放大。

配置和请求组成与 quick 版本相似，但 segment 更长：

| Segment | 时长 | 并发 | 作用 |
| --- | ---: | ---: | --- |
| `warmup` | 300s | 32 | 建立工作集 |
| `steady_reuse` | 600s | 56 | 稳态复用观察 |
| `prefill_main` | 2100s | 80 | 主压力阶段 |
| `cold_churn_burst` | 600s | 88 | 冷流量冲击 |

验证目标：

- 检查 quick 实验中的收益能否在更长时间保持。
- 观察 rebuilt-from-eviction 是否累积。
- 判断 admission 是否过强或过弱。

### 5.3 `qwen3_5_9b_lru_gap_throughput_quick_12m.json`

这个实验专门寻找 LRU 的弱点。

配置要点：

- hot families：32
- sticky sessions：80
- hot family per round：14
- sticky followup per round：6
- cold RAG per round：7
- transient per round：3
- burst every 5 rounds
- decode every 16 rounds
- concurrency：72

请求发送分三个 segment：

| Segment | 时长 | 并发 | 作用 |
| --- | ---: | ---: | --- |
| `warmup` | 120s | 36 | 建立多个 hot families |
| `lru_gap_main` | 480s | 72 | 用冷请求挤压 LRU |
| `revisit_after_churn` | 120s | 76 | 热 family 回访，观察是否被 LRU 误驱逐 |

验证目标：

- 验证“最近没访问但未来会复用”的前缀 family 是否会被 LRU 错误驱逐。
- 检查 family-protect 是否能在 revisit 阶段保住共享主干。

### 5.4 `qwen3_5_9b_working_set_gap_quick_8m.json`

这是最终吞吐主线的前身，也是冻结 throughput controller 的关键 quick run。

配置要点：

- workload：`saturation_throughput_pressure`
- tenants：2
- hot families：8
- sticky sessions：24
- hot family per round：8
- sticky followup per round：3
- cold RAG per round：10
- transient per round：1
- burst every 3 rounds，burst cold requests：8
- decode every 24 rounds
- concurrency：64
- request selection：sequential
- SLO probes：18s、20s、22s、24s、28s、32s、40s

请求发送分三个 segment：

| Segment | 时长 | 并发 | 是否计分 | 请求类型 |
| --- | ---: | ---: | --- | --- |
| `working_set_warmup` | 80s | 32 | 否 | 只包含 `durable_hot_family` 和 `sticky_session_followup` |
| `cold_churn_main` | 280s | 64 | 是 | 全部请求类型，重点加入 cold churn |
| `durable_revisit` | 120s | 68 | 是 | 热 family 和 sticky session 回访 |

验证目标：

- 明确制造“先建立工作集、再被冷流量冲击、最后热请求回访”的完整故事。
- 找出最适合 9B 的 throughput controller 参数。

关键观察：

- 在该 quick run 上，选定 SLO 40s 时，KVFabric goodput 从 1815.04 提升到 3590.21，提升 97.80%。
- prefix hit ratio 从 0.213 提升到 0.309。
- warm-family hit ratio 从 0.414 提升到 0.711。
- rebuilt-from-eviction 从 786 降到 115。

这个结果后来被放大为 120 分钟 final stage。

## 6. 完整长实验：`prefill_throughput_medium`

### 6.1 配置

最终吞吐长实验使用：

- 配置文件：`qwen3_5_9b_prefill_throughput_medium.json`
- 容量：medium，`GPU_MEMORY_UTILIZATION=0.70`
- 策略：`lru` vs `kvfabric_throughput`
- 总时长：120 分钟
- workload：`saturation_throughput_pressure`

核心请求参数：

| 参数 | 值 |
| --- | ---: |
| tenant count | 2 |
| hot family count | 8 |
| sticky session count | 24 |
| rounds | 1200 |
| hot family per round | 8 |
| sticky followup per round | 3 |
| cold RAG per round | 10 |
| transient per round | 1 |
| burst every rounds | 3 |
| burst cold requests | 8 |
| decode every rounds | 24 |

prompt 重复强度：

| 文本片段 | repeat |
| --- | ---: |
| global shared policy | 46 |
| tenant policy | 20 |
| family template | 38 |
| sticky history | 18 |
| cold RAG | 94 |
| burst cold | 112 |
| transient template | 30 |
| decode prompt | 12 |

### 6.2 请求阶段

| Segment | 时长 | 并发 | 是否计分 | 说明 |
| --- | ---: | ---: | --- | --- |
| `working_set_warmup` | 900s | 32 | 否 | 只发 hot family 和 sticky session followup，建立应被保护的工作集 |
| `cold_churn_main` | 4500s | 64 | 是 | 发所有请求类型，大量 cold RAG 和 burst 挤压 KV cache |
| `durable_revisit` | 1800s | 68 | 是 | 热 family 和 sticky sessions 回访，验证前缀是否还在 |

### 6.3 要验证什么

这个实验验证的是 KVFabric 最核心的系统主张：

在中等容量下，冷流量会把 LRU 中暂时不活跃但未来会复用的共享前缀挤掉；KVFabric 通过 hint-aware admission 和 family-aware eviction 少缓存低价值冷请求、保护 durable family 主干，从而减少后续重建，提高 SLO goodput。

### 6.4 已完成结果

| 指标 | LRU | KVFabric | 变化 |
| --- | ---: | ---: | ---: |
| selected SLO goodput | 1815.04 | 3590.21 | +97.80% |
| p50 latency | 40.925s | 32.649s | 改善 |
| p95 latency | 45.707s | 35.977s | 改善 |
| prefix hit ratio | 21.28% | 30.93% | 提升 |
| eligible hit ratio | 37.29% | 66.06% | 提升 |
| warm-family hit ratio | 41.41% | 71.11% | 提升 |
| prefix hit tokens | 7,587,360 | 11,491,920 | 提升 |
| evicted blocks | 81,330 | 54,030 | 减少 |
| rebuilt-from-eviction | 11,790 | 1,725 | -85.37% |

admission 侧观察：

- KVFabric 触发 admission limited 26,115 次。
- saved blocks 68,475。
- 限制主要集中在 `cold_rag_burst` 和 `cold_rag_unique`。

这说明 KVFabric 主要限制低复用冷流量，把容量留给 durable hot family 和 sticky session。

## 7. rebuilt pressure 实验

### 7.1 `qwen3_5_9b_rebuilt_quick_12m.json`

这是 12 分钟重建压力 quick test。

配置要点：

- hot families：18
- sticky sessions：72
- hot family per round：14
- sticky followup per round：8
- cold RAG per round：8
- transient per round：3
- burst every 7 rounds，burst cold requests：5
- decode every 12 rounds
- concurrency：72

segment：

| Segment | 时长 | 并发 | 作用 |
| --- | ---: | ---: | --- |
| `warmup` | 120s | 32 | 建立 hot family |
| `eviction_churn` | 480s | 72 | 用冷流量制造驱逐 |
| `revisit_after_churn` | 120s | 64 | 回访 hot family，统计 rebuilt-from-eviction |

验证目标：

- 专门观察被驱逐的 prefix block 后续是否又被同 family 请求需要。
- 评估 `rebuilt-from-eviction` 作为反馈指标是否敏感。

### 7.2 `qwen3_5_9b_rebuilt_pressure_30m.json`

这是 30 分钟放大版本。

segment：

| Segment | 时长 | 并发 |
| --- | ---: | ---: |
| `warmup` | 180s | 32 |
| `reuse_probe` | 360s | 56 |
| `eviction_churn` | 900s | 72 |
| `revisit_after_churn` | 360s | 64 |

验证目标：

- 判断 rebuilt feedback 是否在更长时间内稳定。
- 为后续是否采用 `kvfabric_rebuilt` profile 提供依据。

最终主矩阵没有把 rebuilt pressure 单独作为主结果，是因为 final throughput stage 已经同时包含冷流量冲击、热 family 回访和 rebuilt 指标，而且解释更完整。

## 8. saturation / SLO boundary 实验

### 8.1 `qwen3_5_9b_saturation_medium_60m.json`

这是 60 分钟中等容量饱和实验。

配置要点：

- tenants：6
- hot families：64
- sticky sessions：512
- hot family per round：10
- sticky followup per round：6
- cold RAG per round：6
- transient per round：3
- burst every 5 rounds
- decode every 2 rounds
- concurrency：56

segment：

| Segment | 时长 | 并发 | 作用 |
| --- | ---: | ---: | --- |
| `warmup` | 240s | 24 | 建立工作集 |
| `low_guard` | 300s | 20 | 低压保护段，检查不退化 |
| `high_main` | 2700s | 48 | 主高压阶段 |
| `red_burst` | 360s | 64 | 红线突发压力 |

验证目标：

- 检查接近系统饱和时，KVFabric 是否能把更多请求推入 SLO 内。
- 观察高压下 goodput 提升是否来自 cache 质量改善，而不只是请求数量差异。

### 8.2 `qwen3_5_9b_saturation_reuse_proof_30m.json`

这是 30 分钟复用证明实验。

配置要点：

- tenants：4
- hot families：12
- sticky sessions：64
- hot family per round：16
- sticky followup per round：12
- cold RAG per round：2
- transient per round：1
- burst every 8 rounds
- decode every 6 rounds
- concurrency：52

验证目标：

- 在更明确的高复用场景中，验证 prefix hit 和 SLO goodput 的关联。
- 避免只用极端 cold churn 解释收益。

这些 saturation 实验帮助确定：9B 的亮点不应该只讲 raw tokens/s，而应该讲 SLO goodput、prefix cache 质量和 rebuilt-from-eviction。

## 9. 延迟实验：从普通交互到 foreground-priority

### 9.1 `qwen3_5_9b_interactive_latency_quick_12m.json`

这是早期 12 分钟交互延迟实验。

配置要点：

- trace profile：`daily_dedicated_reuse`
- duration：720s
- target rate：0.72 req/s
- max in flight：56
- session reuse probability：0.90
- SLO：60s

请求组成：

- `short_chat_qa`：短聊天问答。
- `tenant_workflow_hot`：租户工作流热请求。
- `deep_multi_turn_chat`：较长多轮聊天。
- `project_code_followup`：代码/项目上下文追问。
- `long_doc_research_followup`：长文档研究追问。
- `agent_tool_loop`：工具调用式多轮任务。

验证目标：

- 检查 scheduler affinity / latency protection 是否能改善交互请求。

早期问题：

- queue pressure 不足。
- headers 不完整。
- promotion 次数少，效果不明显。

### 9.2 `qwen3_5_9b_interactive_latency_queue_quick_10m.json` 和 45m 版本

这是增加 queue pressure 的版本。

配置要点：

- target rate：0.9 req/s
- max in flight：96
- session reuse probability：0.72
- 加入 background / decode 类请求。

请求组成除了前台类，还加入：

- `background_cold_lookup`
- `decode_heavy_background`

验证目标：

- 制造更明显的排队竞争，让 scheduler promotion 有发挥空间。
- 检查 KVFabric 是否能把高优先级前台请求提前。

这一阶段发现，只把背景类混在同一个权重池里还不够清晰，前台和后台竞争不稳定。

### 9.3 `qwen3_5_9b_foreground_latency_background_quick_8m.json`

这是 foreground/background 独立注入的 quick 版本。

配置要点：

- trace profile：`daily_dedicated_reuse`
- duration：480s
- target rate：0.9 req/s
- max in flight：96
- background mix probability：0.2
- SLO：60s

前台 class weights：

| Class | 权重 |
| --- | ---: |
| `short_chat_qa` | 0.20 |
| `tenant_workflow_hot` | 0.18 |
| `agent_tool_loop` | 0.20 |
| `project_code_followup` | 0.18 |
| `deep_multi_turn_chat` | 0.14 |
| `long_doc_research_followup` | 0.10 |

后台 class weights：

| Class | 权重 |
| --- | ---: |
| `background_cold_lookup` | 0.45 |
| `decode_heavy_background` | 0.55 |

请求发送逻辑：

- trace 正常按时间生成前台请求。
- 以 0.2 概率独立插入后台请求。
- 前台请求带高优先级、session/family/SLO hints。
- 后台请求带低优先级或低复用 hints。

验证目标：

- 明确验证“前台交互请求保护”，而不是笼统优化所有请求。

### 9.4 `qwen3_5_9b_foreground_latency_background_90m.json`

这是最终延迟长实验。

配置要点：

- duration：5400s
- target rate：0.9 req/s
- max in flight：96
- warmup：120s
- background mix probability：0.2
- 策略：`lru` vs `kvfabric_latency`
- capacity：medium

KVFabric latency profile：

- admission strength：0
- eviction strength：0
- scheduler affinity strength：1.0
- SLO protect strength：0.9

这样设计是为了把变量集中在 scheduler，而不是把 admission / eviction 收益混进延迟结论。

最终结果：

| 指标 | LRU | KVFabric | 变化 |
| --- | ---: | ---: | ---: |
| request goodput | 106.38 | 423.34 | +297.96% |
| e2e goodput | 106.38 | 305.23 | +186.94% |
| service p50 | 132.337s | 69.757s | 改善 |
| service p95 | 223.615s | 203.591s | 改善 |
| e2e p50 | 153.822s | 80.727s | 改善 |
| e2e p95 | 273.888s | 221.542s | 改善 |
| latency promotions | 0 | 3,442 | 生效 |

前台类 e2e p95 全部显著改善：

| Class | LRU e2e p95 | KVFabric e2e p95 | 改善 |
| --- | ---: | ---: | ---: |
| `agent_tool_loop` | 246.209s | 136.808s | 44.43% |
| `deep_multi_turn_chat` | 242.968s | 133.376s | 45.11% |
| `long_doc_research_followup` | 245.434s | 150.830s | 38.55% |
| `project_code_followup` | 266.814s | 178.573s | 33.07% |
| `short_chat_qa` | 196.477s | 91.316s | 53.52% |
| `tenant_workflow_hot` | 218.928s | 89.736s | 59.01% |

后台类有退化，应在汇报中主动说明：

| Class | LRU e2e p95 | KVFabric e2e p95 |
| --- | ---: | ---: |
| `background_cold_lookup` | 217.490s | 245.073s |
| `decode_heavy_background` | 330.395s | 355.577s |

实验结论：

KVFabric latency profile 适合前台交互和后台任务混部的服务场景。它通过 scheduler promotion 把更有 SLO 价值的前台请求提前，代价是部分后台低优先级请求延迟上升。

## 10. 企业普通混合实验

### 10.1 `qwen3_5_9b_enterprise_normal_25m.json`

这是 25 分钟企业混合 quick / mid test。

配置要点：

- trace profile：`enterprise_mixed`
- duration：1500s
- target rate：0.75 req/s
- max in flight：48
- session reuse probability：0.62
- hint regime：partial hints
- SLO：90s

请求组成：

- 多租户请求，tenant count 较多。
- 一部分 hot workflow / family 会重复。
- 一部分 session 会多轮复用。
- 还有大量普通冷查询和低复用请求。

验证目标：

- 检查 KVFabric 在普通企业混合流量下是否不过度牺牲 baseline。
- 验证 hint-aware admission 是否能温和工作，而不是只在强构造场景中有效。

### 10.2 `qwen3_5_9b_enterprise_normal_75m.json`

这是最终矩阵中的企业普通混合 guard stage。

配置要点：

- duration：4500s
- target rate：0.75 req/s
- actual trace 约 0.922 req/s
- max in flight：48
- session reuse probability：0.62
- partial hints
- tenants：约 10
- clients：64
- families：约 917

验证目标：

- 证明 KVFabric 在更普通、更分散的企业混合流量下不会为了保护共享前缀而引入明显负担。
- 这个实验用于验证策略边界和工程稳健性，收益规模不是主要目标。

截至本文记录，最终本地 summary 以前两个 stage 为主，enterprise tail 结果需要以最终同步目录为准。

## 11. 低复用非回归实验

### 11.1 `qwen3_5_9b_low_reuse_low_frequency_20m.json`

这是 20 分钟低复用 quick test。

配置要点：

- trace profile：`low_reuse_low_frequency`
- duration：1200s
- target rate：0.25 req/s
- max in flight：16
- session reuse probability：0.10
- cold family reuse probability：0
- SLO：120s

请求组成：

- 大多数请求都是唯一 family。
- session reuse 很低。
- 几乎没有 durable hot family。
- 请求频率也低，不容易形成明显 cache pressure。

验证目标：

- 检查 KVFabric 在“没有复用价值”的场景下是否少介入。
- 验证 admission 不应错误地为低复用场景制造收益假象。

### 11.2 `qwen3_5_9b_low_reuse_45m.json`

这是最终矩阵中的低复用 guard stage。

配置要点：

- duration：2700s
- target rate：0.25 req/s
- max in flight：16
- session reuse probability：0.10
- cold family reuse probability：0
- capacity：large
- 策略：`lru` vs `kvfabric_admission`

为什么使用 large capacity：

- 低复用场景本来不应该有太多可保护前缀。
- 如果用 small capacity，可能把容量不足造成的波动误解为策略效果。
- large capacity 能更纯粹地验证“不该优化时少打扰”。

验证目标：

- 非回归。
- 少消耗。
- 不为低复用请求制造额外调度或 admission 副作用。

截至本文记录，该 stage 属于 final tail guard，最终数值需要以同步后的 summary 为准。

## 12. sticky burst 实验

### `qwen3_5_9b_sticky_burst_45m.json`

这是 45 分钟 sticky session burst 实验。

配置要点：

- trace profile：`sticky_burst`
- duration：2700s
- target rate：0.62 req/s
- max in flight：64
- session reuse probability：0.78
- SLO：120s

请求组成：

- session 粘性较强。
- burst 阶段会集中出现多个相关请求。
- 同一 tenant / session / family 的前缀可能短时间内多次复用。

验证目标：

- 检查 KVFabric 在 bursty 会话流量中是否能保住最近形成的工作集。
- 这个实验介于 throughput 和 latency 之间，适合作为探索实验，不是最终主矩阵核心 stage。

## 13. 最终 12 小时矩阵

最终长周期实验被简化为四个 stage，避免过大的矩阵让结果分散。

| Stage | 配置 | 容量 | 策略 | 时长 | 角色 |
| --- | --- | --- | --- | ---: | --- |
| `prefill_throughput_medium` | `qwen3_5_9b_prefill_throughput_medium.json` | medium | `lru` vs `kvfabric_throughput` | 120m / policy | 主吞吐和 SLO goodput 结果 |
| `interactive_latency_medium` | `qwen3_5_9b_foreground_latency_background_90m.json` | medium | `lru` vs `kvfabric_latency` | 90m / policy | 前台延迟保护结果 |
| `enterprise_normal_medium` | `qwen3_5_9b_enterprise_normal_75m.json` | medium | `lru` vs `kvfabric_admission` | 75m / policy | 普通企业混合 guard |
| `low_reuse` | `qwen3_5_9b_low_reuse_45m.json` | large | `lru` vs `kvfabric_admission` | 45m / policy | 低复用非回归 guard |

### 13.1 为什么不是把所有实验都放进最终矩阵

早期矩阵曾包含 raw throughput、SLO boundary、rebuilt pressure、daily dedicated、capacity sweep、enterprise normal、low reuse 等多个 stage。后来删减的原因是：

- 很多 stage 是调参或定位问题用的，不适合作为最终主结论。
- throughput stage 已经同时覆盖 cold churn、durable revisit、prefix hit、rebuilt-from-eviction。
- latency stage 已经单独证明 scheduler protection，不需要和吞吐策略混在一起。
- enterprise 和 low reuse 作为 guard 更清楚，证明策略边界。

最终矩阵的逻辑更适合汇报：

1. 高压共享前缀场景：KVFabric 有显著收益。
2. 前台交互混部场景：KVFabric 能保护前台延迟。
3. 普通企业混合场景：KVFabric 应温和、不乱动。
4. 低复用场景：KVFabric 应少介入、不退化。

## 14. PPT 汇报建议

9B 实验部分可以按以下方式讲：

第一页讲实验平台：2 x RTX 3090、Qwen3.5-9B、vLLM OpenAI server、medium capacity、LRU vs KVFabric。

第二页讲请求发送方式：所有请求都是真实 `/v1/chat/completions`，带 messages 和 `x-kvfabric-*` headers，控制面读取 hints 做 admission / eviction / scheduler。

第三页讲 workload 设计：hot family、sticky session、cold RAG、burst cold、transient template、decode-heavy，解释每一类请求为什么存在。

第四页讲主吞吐实验三阶段：warmup 建工作集、cold churn 冲击、durable revisit 回访。配一张流程图最清楚。

第五页放吞吐结果：SLO goodput +97.80%，rebuilt-from-eviction -85.37%，prefix hit ratio 提升。

第六页讲延迟实验：前台请求和后台请求混部，scheduler promotion 保护前台 SLO。

第七页放前台类 e2e p95 表格，强调 6/6 前台类均改善 30% 以上，同时说明后台类有代价。

第八页讲 guard 实验：enterprise normal 和 low reuse 用来证明策略边界，不是所有场景都强行优化。

这样讲可以避免把实验说成“随机压测”，而是清楚表达：每个实验都对应一个系统资源管理问题。
