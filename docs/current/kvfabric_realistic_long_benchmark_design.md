# KVFabric 真实化长压测试设计

日期：2026-06-24

目标环境：vLLM 0.22.1 overlay，`qwen3_5_27b` / `Qwen/Qwen3.5-27B-FP8`，
远程 `robowalker`，2 x RTX 3090 24GB。

更新说明：本文保留为 realistic trace 设计记录。正式 12h 验收和 30% 吞吐提升路线以
`docs/current/kvfabric_12h_acceptance_experiment_design.md` 和
`docs/current/kvfabric_30pct_throughput_refactor_research.md` 为准。

## 目标

下一阶段长压测试需要把两个问题分开回答：

1. 在中小型企业 LLM 服务中，KVFabric 是否能利用稳定租户前缀、RAG、agent
   和多轮会话，提高 KV cache 质量、吞吐和尾延迟？
2. 在更通用的大模型网关中，大量请求没有可复用前缀、还有一部分 decode-heavy
   请求时，KVFabric 是否至少不退化，并在可复用子场景中有收益？

当前 10 小时 `hint_pressure` 长压结果适合作为策略验证，但不足以直接宣称
“真实生产通用加速”。它是合成的、prefill-heavy 的、closed-loop 的，并且使用
近似 oracle 的请求 hint。下一版测试要保留 KV cache 压力和策略可解释性，同时补上：

- 更真实的请求类别和输出长度；
- open-loop / trace replay 到达过程；
- 多轮会话和长上下文历史增长；
- RAG 热文档、冷文档和伪共享文档的区分；
- hint 缺失和 hint 错误；
- warmup 剔除、class/session/family 级别指标。

## 外部资料依据

公开资料通常不给“所有生产 LLM 服务的任务类型占比”这种唯一答案。更可靠的做法是
使用公开 trace 和 workload profile 给出的约束，再把本项目的 profile 权重显式写清楚。

- BurstGPT 公开分析了一个区域 Azure LLM 服务 213 天、约 1031 万请求的 trace。
  其中 API 类入口在该 trace 中占主导，对话类入口较少；对话服务有明显周周期和日周期，
  API 服务更偏非周期和突发。它还报告：超过 35% 的 conversation 只有 1 个请求，
  median conversation length 为 2，75% 的 conversation 不超过 4 个请求。
  来源：<https://arxiv.org/html/2401.17644v4>。
- ServeGen 总结真实 LLM serving workload 具有突发性、client skew 和异质性。它给出
  输入长度更适合用 Pareto + lognormal 混合建模，输出长度可用 exponential 分布建模；
  还报告多轮会话在其 trace 中按数量是少数，平均 conversation length 约 3.5，
  inter-turn time 约 100 秒。来源：<https://arxiv.org/html/2505.09999v2>。
- IETF workload profile draft 把 LLM serving 场景拆成 search/fact recall、RAG、
  long-document QA、summarization、extraction/classification、code、decode-heavy
  content generation、agent/tool workflow 等 profile，并给出不同输入/输出范围。
  来源：<https://datatracker.ietf.org/doc/draft-mondal-llm-serving-workload-profiles/00/>。
- vLLM automatic prefix caching 的收益来自共享 prefix 的 prefill 复用；没有共享前缀、
  或主要耗时在长输出 decode 时，prefix caching 的 leverage 会下降。
  来源：<https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/>。
- SGLang/RadixAttention 把 multi-turn chat、RAG、agent、few-shot、
  self-consistency、tree-of-thought 都视为常见共享 prompt 结构，并展示了 cache-aware
  execution 在这些模式下的价值。来源：<https://www.lmsys.org/blog/2024-01-17-sglang/>。

这些资料给出的约束是：下一版 benchmark 需要覆盖三类 regime：

1. 通用网关混合流量：可复用比例较低，请求类型更杂，有 decode-heavy 尾部。
2. 企业 RAG/agent 流量：稳定租户、稳定业务 workflow、RAG 冷热文档、agent/tool loop。
3. 高复用长上下文会话流量：多轮对话和 long-doc follow-up QA，prefix 复用理论上很高。

## 当前 10 小时长压实际测到什么

当前正式长压使用：

```text
experiments/long_pressure_benchmark/configs/qwen3_5_27b_hint_pressure_10h.json
```

它的实际结构是：

- 6 个 tenant；
- 32 个 durable hot family；
- 98,922 条 payload；
- 类别比例约为 38% hot durable family、42% cold RAG、19% transient ambiguous
  family、不到 1% burst cold；
- 固定 `max_tokens=32`；
- 平均 prompt 长度约 2.2k tokens；
- closed-loop concurrency 10，即 worker 完成一条请求后立刻发下一条；
- 从整个 payload pool 全局 shuffle 取请求；
- HTTP header 中提供完整 class、family、priority、expected reuse hint；
- 远程正式参数为 `max_model_len=4096`、`max_num_seqs=10`、
  `max_num_batched_tokens=16384`。

这个设计很好地验证了：

- 低复用 cold RAG 是否污染 cache；
- `shared_aware` / `family_protect` 是否减少错误驱逐；
- hint-aware admission 是否能节省低价值 blocks；
- rebuilt-from-eviction 是否下降；
- 4096 长度下 27B-FP8 在 2 x 3090 上能否长期稳定运行。

但它还不能完整代表生产：

- 它是 prefill-heavy，几乎没有长输出 decode 压力；
- prompt 内容是模板合成文本，不是真实用户、真实文档、真实代码或真实多轮对话；
- 全局 shuffle 会破坏 session/revisit/burst 的真实时间局部性；
- `warmup_seconds` 目前只是记录字段，没有从最终指标中剔除；
- hint 几乎完全正确，真实网关往往只有部分 hint，甚至有错 hint；
- durable hot family 更像稳定模板，不是上下文逐轮增长的多轮对话。

## 多轮长上下文是否已经被模拟

当前没有很好模拟长上下文多轮对话。

真实 chat completion 多轮场景通常是：客户端每一轮都把完整历史重新发送给服务端。
因此第 `n+1` 轮请求包含第 `n` 轮的大部分 prompt，再加上新的 user/assistant 内容。
如果同一 session 的后续 turn 到来时，前一轮 KV blocks 还留在 GPU cache 中，
prefix reuse 会很高。

但“多轮对话天然高复用”有几个前提：

- session 的后续 turn 到达间隔不能太长；
- 同一 session 中间不能插入过多冷 RAG 或其他租户长 prompt；
- 客户端稳定地把上轮 assistant 输出原样带回；
- system prompt、tool schema、历史格式不能频繁漂移；
- scheduler 最好能感知 session/family affinity，让同一 session 的 follow-up 不被冷流量长期挤开。

因此下一版测试显式建模：

- `session_id`；
- `turn_index`；
- `inter_turn_delay`；
- `history_tokens`；
- session 是否活跃；
- turn 级 prefix hit；
- 冷流量冲刷后 follow-up 是否 rebuild。

## 自对话 trace 的使用方式

自对话适合用来离线生成 transcript，不适合作为正式 A/B benchmark 的在线生成方式。

如果让模型在 benchmark 过程中实时自我对话，不同策略会生成不同 assistant 内容，
后续 turn 的 prompt 就不再相同。这样 LRU、shared-aware、family-protect 的输入不一致，
吞吐差异会混入“模型生成了不同历史”的变量，A/B 不干净。

采用“离线自对话生成 + 固定 trace replay”：

1. 先用固定模型、固定 seed、固定 prompt template 生成一批 session transcripts。
2. 把每个 session 的每一轮 user/assistant 历史冻结下来。
3. 正式 benchmark 中，第 `k` 轮请求发送完全相同的 message history。
4. 所有 policy 使用同一个 trace 文件和同一批 prompt payload。

live self-dialogue soak 可以作为稳定性观察项。正式性能比较使用 frozen transcript。

## 推荐的会话深度分布

公开 trace 显示很多 conversation 很短，因此三套 profile 使用不同会话深度分布：

| Session depth | 通用网关 | 企业混合 | 多轮高复用压力 |
|---:|---:|---:|---:|
| 1 turn | 35% | 25% | 10% |
| 2 turns | 25% | 25% | 15% |
| 3-4 turns | 25% | 30% | 30% |
| 5-8 turns | 12% | 15% | 30% |
| 9-16 turns | 3% | 5% | 15% |

通用网关 profile 贴近“多数 conversation 很浅”的公开 trace 信号；
多轮高复用压力 profile 则专门测试 KVFabric 能否抓住高 prefix reuse 的上限场景。

## 请求类别 Profile

下面的占比是本项目采用的测试假设，报告中记录 seed 和 trace hash 以便复现。

### Profile A：General Gateway 10h

用于回答：KVFabric 在更通用的大模型网关上是否不退化。

| Class | Share | Input tokens | Output tokens | Reuse 预期 |
|---|---:|---:|---:|---|
| `short_chat_qa` | 25% | 64-768 | 32-256 | 低到中 |
| `single_turn_api_task` | 20% | 128-2048 | 32-512 | 低 |
| `rag_qa` | 15% | 1024-4096 | 64-768 | 文档重复时中等 |
| `summarization_extract` | 15% | 1024-4096 | 64-512 | 低到中 |
| `code_assist` | 10% | 512-4096 | 128-1024 | repo context 重复时中等 |
| `multi_turn_chat` | 10% | 256-4096 增长 | 32-512 | active session 内高 |
| `decode_heavy_content` | 5% | 128-2048 | 512-2048 | 低 |

预期：KVFabric 在该 profile 下以不退化为底线；如果存在稳定 session/doc reuse，5-15%
提升属于可信范围。
如果在这个 profile 下宣称 +30%，需要非常强的 class-level 证据。

### Profile B：Enterprise RAG/Agent 10h

用于代表中小型企业内部服务：租户稳定、业务模板稳定、RAG 冷热混合、agent/tool loop。

| Class | Share | Input tokens | Output tokens | Reuse 预期 |
|---|---:|---:|---:|---|
| `tenant_workflow_hot` | 20% | 1024-4096 | 32-384 | 高，durable prefix |
| `rag_qa_hot_docs` | 15% | 2048-4096 | 64-768 | 中到高 |
| `rag_qa_cold_docs` | 25% | 2048-4096 | 64-768 | 无 |
| `agent_tool_loop` | 15% | 1024-4096 增长 | 32-512/step | 高 |
| `multi_turn_support` | 15% | 512-4096 增长 | 32-512 | session 内高 |
| `extraction_classification` | 5% | 512-4096 | 16-256 | 低 |
| `decode_heavy_report` | 5% | 512-2048 | 512-1536 | 低 |

预期：这是当前 KVFabric 最合理的生产目标场景。高压力下如果 admission 和 scheduler
不让 cold RAG 污染 durable prefixes，15-30% 提升是有可能的。

### Profile C：Sticky Conversation / Long Context 4-6h

用于专门回答：长上下文多轮对话和 follow-up QA 下，prefix reuse 高时 KVFabric 能否显著放大收益。

| Class | Share | Input tokens | Output tokens | Reuse 预期 |
|---|---:|---:|---:|---|
| `deep_multi_turn_chat` | 45% | 512-4096 增长 | 32-512 | 很高 |
| `long_doc_followup_qa` | 25% | 2048-4096 | 64-768 | 同文档内高 |
| `agent_tool_loop` | 15% | 1024-4096 增长 | 32-512 | 高 |
| `cold_rag_noise` | 10% | 2048-4096 | 32-512 | 无 |
| `decode_heavy_noise` | 5% | 512-2048 | 512-1536 | 无 |

预期：总 prefix-hit tokens 应明显高于当前 10h run 的 13% 左右。如果这里仍然没有明显收益，
说明策略还没有真正保护 session/document 级 prefix。

## 输入和输出长度分布

正式长压不应再固定 `max_tokens=32`。

采用：

- 输入长度按 class 使用 Pareto + lognormal 混合分布，再按 `max_model_len` 截断；
- 输出长度按 class 使用 exponential 或 lognormal tail；
- 保留 decode-heavy tail，让 TPOT、decode batch 和 tail latency 进入测量；
- qwen3_5_27b 在 2 x 3090 上，正式默认仍用 `max_model_len=4096`；
- 8192 token 可用于 smoke 或小模型验证；27B 正式通过条件仍以显存稳定的 4096 token
  配置为主。

推荐输出范围：

| Class group | `max_tokens` 范围 |
|---|---|
| short QA / extraction | 16-256 |
| RAG / summarization | 64-768 |
| support chat / workflow | 32-512 |
| code assist | 128-1024 |
| agent step | 32-512 |
| decode-heavy content | 512-2048 |

## 到达模型

下一版正式 benchmark 应以 trace replay / open-loop 为主。closed-loop 最大吞吐测试仍然保留，
但不能作为“真实流量”的主结论。

### Trace JSONL 格式

先生成静态 trace，再对所有 policy replay 同一个 trace：

```json
{
  "request_id": "req-000001",
  "scheduled_at_seconds": 12.345,
  "tenant_id": "tenant-03",
  "client_id": "client-117",
  "session_id": "sess-0042",
  "family_id": "support-router-v2",
  "turn_index": 3,
  "request_class": "multi_turn_support",
  "expected_reuse": "durable",
  "cache_priority": "high",
  "prompt_ref": "prompts/000001.json",
  "max_tokens": 384,
  "temperature": 0.0
}
```

loadgen 按 `scheduled_at_seconds` 发请求。如果服务端跟不上，记录 send delay、
queueing delay、drop/timeout，而不是静默退化为 closed-loop。

### Load modes

每个 profile 至少三种负载：

| Mode | 目的 | 到达行为 |
|---|---|---|
| `steady_70` | 稳态服务 | 约等于 baseline 饱和能力 70% |
| `stress_90` | 真实高压 | 约等于 baseline 饱和能力 90%，带 burst |
| `overload_105` | 边界压力 | 约等于 baseline 饱和能力 105%，跑 30-60 分钟 |

trace 生成应包含：

- client-level skew：少数租户/客户端贡献大量请求；
- per-client burstiness：使用 Gamma/Weibull 或经验 burst，避免只用固定并发；
- session stickiness：同一 session 后续 turn 通常在 10-180 秒后到达；
- epoch/diurnal scaling：10 小时以上 run 里模拟负载涨落；
- cold RAG burst：真实时间窗口内集中到来，而不是只在全局 shuffle 中随机散落。

## 数据构造

### Prompt 来源

1. 合成的稳定 system/tool/schema 前缀：适合模拟企业应用 scaffolding。
2. 冻结的自对话 transcript：用于多轮 chat，正式 A/B replay。
3. 本地文档 chunks：用于 RAG 和 long-doc QA，可以来自公开文档、wiki 风格文章、
   代码文档、或生成的企业记录。
4. 预生成 tool observations：用于 agent/tool loop，不在 benchmark 中实时调外部工具。
5. decode-heavy prompt：用于避免测试只测 prefill。

### RAG 文档复用模型

RAG 不应只有 `cold_rag` 一个类，应拆成：

- `hot_doc_rag`：同一文档或 chunk set 在一个时间窗口内被问 3-20 次；
- `tenant_doc_rag`：同一 tenant policy prefix，不同文档；
- `cold_doc_rag`：一次性文档，不应深度缓存；
- `near_duplicate_doc_rag`：开头 boilerplate 类似，但正文尾部不同，用来测试伪共享误保护。

### Prompt drift

真实应用的 prefix 不总是 byte-identical。trace 中加入：

| Drift mode | Share | 含义 |
|---|---:|---|
| `exact` | 70% | 稳定模板和历史 |
| `minor_format` | 15% | 空格、日期、trace id、无害 label 变化 |
| `versioned_schema` | 10% | schema/tool 版本变化 |
| `semantic_shift` | 5% | family_id 可能相同，但语义上不应复用 |

summary 按 drift mode 报告结果，避免策略只在完全相同 prompt 上显得有效。

## Hint 质量矩阵

当前 hint benchmark 是 perfect hints。下一版要测：

| Regime | 描述 | 目的 |
|---|---|---|
| `no_hints` | 不发 KVFabric headers | 看无 hint 推断能力 |
| `partial_hints` | 有 tenant/session，缺 reuse class | 更接近普通网关 |
| `noisy_hints` | 10-20% priority/reuse 错误 | 鲁棒性 |
| `full_hints` | 当前完整 class/family/reuse headers | 能力上限 |

生产可信结论应主要来自 `partial_hints` 或 `noisy_hints`，不能只依赖 `full_hints`。

## 27B 远程长压矩阵

所有 policy 使用同一个 trace hash：

- `lru`
- `shared_aware`
- `family_protect`
- 后续新的 scheduler-positive-selection policy

推荐初始矩阵：

| Suite | 每个 policy 时长 | Profile | Load mode | Hint regime |
|---|---:|---|---|---|
| `enterprise_mixed_smoke` | 600s | Enterprise RAG/Agent | `steady_70` | `partial_hints` |
| `enterprise_mixed_10h` | 12000s | Enterprise RAG/Agent | `stress_90` | `noisy_hints` |
| `general_gateway_10h` | 12000s | General Gateway | `stress_90` | `partial_hints` |
| `conversation_sticky_4h` | 4800s | Sticky Conversation | `stress_90` | `partial_hints` |
| `no_hint_enterprise_2h` | 2400s | Enterprise RAG/Agent | `stress_90` | `no_hints` |
| `overload_boundary_1h` | 3600s | Enterprise RAG/Agent | `overload_105` | `noisy_hints` |

2 x RTX 3090 24GB 初始配置：

- 默认 `max_model_len=4096`；
- 初始 `max_num_seqs=8` 或 `10`；
- broad mix 用 `max_num_batched_tokens=8192` 起步；
- prefill-heavy 稳定后再试 `16384`；
- 完整 `kvfabric_lifecycle.jsonl` 保留本地，不提交 Git；
- 提交 trace summary、metrics、rolling samples、class/session/family summary。

## 报告指标

### Load / latency

- offered requests/s 与 completed requests/s；
- offered tokens/s 与 completed tokens/s；
- open-loop send delay / queueing delay；
- TTFT、TPOT、E2E p50/p95/p99；
- goodput under SLO，例如 TTFT < 5s 且 E2E < 30s；
- error、timeout、drop rate。

### Cache quality

- prefix hit tokens / prefix hit rate，全局和按 class；
- session/document/family 级 prefix hit；
- reused blocks 的年龄和深度；
- rebuilt-from-eviction blocks；
- class/family 级 regret rate；
- later-useful evicted blocks；
- admission limited blocks；
- admission false negative：被 bypass/limited 后后来又出现复用。

### Scheduler / fairness

- scheduler defers by reason/class；
- 每 tenant throughput/latency；
- 高优先级 session 与 cold RAG 的 tail latency；
- starvation count；
- max defer count；
- active queue depth；
- waiting time distribution。

### Conversation-specific

- session turn depth 分布；
- inter-turn delay 分布；
- prefix-hit rate by turn index；
- 前 N 轮保持 cache-resident 的 session 比例；
- first turn 与 follow-up turn 的 latency 差异；
- cold RAG burst 后 follow-up 是否 rebuild。

## 成功标准

不同 workload 使用不同验收口径：

| Suite | 合理预期 |
|---|---|
| General Gateway | 不退化；5-15% 已有意义 |
| Enterprise RAG/Agent | 高压力下 15-30% 合理 |
| Sticky Conversation | prefix-hit 应很高，可能出现 30%+ |
| No Hints | cache quality 仍应改善，吞吐收益可小 |
| Noisy Hints | 无明显退化；错 hint 的影响可见 |
| Overload Boundary | 应改善 goodput 或尾延迟，而不只是 raw tok/s |

如果只有 `full_hints` + `conversation_sticky` 能到 +30%，结论限定为
“高复用、有较准业务 hint 的上限场景”。

## 实施计划

### Phase 1：Trace generator

新增：

```text
experiments/long_pressure_benchmark/examples/generate_realistic_trace.py
experiments/long_pressure_benchmark/examples/online_trace_loadgen.py
experiments/long_pressure_benchmark/examples/online_duration_loadgen.py
```

输出：

- `trace.jsonl`
- `prompts/*.json`
- `trace_summary.json`
- `trace_summary.md`
- token histogram；
- class / tenant / client / session / family 分布；
- trace hash。

### Phase 2：Open-loop loadgen

新增：

```text
experiments/long_pressure_benchmark/examples/online_trace_loadgen.py
```

要求：

- 读取 `trace.jsonl`；
- 按 `scheduled_at_seconds` 发送；
- 支持最大 in-flight cap；
- 记录 send delay、queueing delay、server latency；
- 支持 closed-loop saturation fallback，但不能混入正式 trace 结果；
- 根据 hint regime 生成 KVFabric headers。

### Phase 3：Remote launchers

新增：

```text
experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh
experiments/long_pressure_benchmark/scripts/run_remote_27b_trace_long_benchmark.sh
experiments/long_pressure_benchmark/scripts/run_remote_27b_hint_pressure_10h_benchmark.sh
```

每个 launcher 在 A/B 前先生成或校验 trace，并把 trace hash 写入 run metadata。

### Phase 4：Summary

扩展：

```text
experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py
```

新增报告：

- offered-load metrics；
- trace hash/profile；
- warmup-excluded 和 full-run 两套指标；
- class/session/family 表；
- hint quality regime；
- conversation-specific metrics。

## 后续测试入口

当前主线转到 12h formal suites：

```text
saturation_throughput_12h
enterprise_mixed_trace_12h
sticky_conversation_trace_12h
```

其中 sticky conversation 专门回答：当长上下文多轮对话的 prefix reuse 很高时，
KVFabric 是否真正保住并利用了 session/document prefix。正式 A/B 使用冻结自对话
transcripts。

## 结论

当前长压证明了 KVFabric 能在合成 prefill-heavy、高 hint 质量的压力流量中减少低复用污染，
并把 shared-aware 的吞吐提升做到约 17%。下一阶段 benchmark 应转向 trace-based、
open-loop、class-balanced、session-aware 设计，同时覆盖通用网关、企业 RAG/agent、
高复用多轮长上下文三类 profile。

只有在这三类 profile 下分别报告 class/session/family 级指标，才能判断收益到底来自
真实生产可复用结构，还是来自当前 benchmark 对策略形状的偏置。
