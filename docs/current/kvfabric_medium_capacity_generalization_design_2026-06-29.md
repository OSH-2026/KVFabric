# KVFabric 中等容量与通用性增强实验设计

日期：2026-06-29

## 目标

这份文档回答四个问题：

1. 能否把正式实验从“KV cache 紧张”改成“KV cache 中等或正常容量”。
2. 如何把高压下 SLO goodput 明显提升作为第一性能目标。
3. 如何把少用户长会话、多轮长文档、agent follow-up 等合适场景下的 TTFT/e2e latency 明显降低作为第二性能目标。
4. 如何用最小必要的 capacity sweep 和非回归测试支撑通用性，而不是让诊断项稀释主性能目标。

本文最初用于设计评审；2026-06-29 已按该方案落地第一版代码与实验配置。后续结果分析仍以实际 run 的容量指标、e2e latency、SLO goodput 和 lifecycle metrics 为准。

## 2026-06-29 落地状态

已新增/修改的核心内容：

- 新模型 profile：`vllm_baseline/profiles/qwen3_5_9b.env`，默认 `MODEL_ID=Qwen/Qwen3.5-9B`、`MAX_MODEL_LEN=4096`、`GPU_MEMORY_UTILIZATION=0.70`、TP=2。
- 新 trace profile：`daily_dedicated_reuse`、`sticky_burst`、`low_reuse_low_frequency`，支持配置 tenant/client/family 数、session 复用概率、follow-up 间隔和 burst 概率。
- 新 trace 指标：`e2e_latency_*`、`e2e_slo_*`、`e2e_goodput_total_tokens_per_second`，并输出到 final metrics、rolling metrics、class metrics 和 raw sample。
- 新配置：`qwen3_5_9b_capacity_sweep_6m.json`、`qwen3_5_9b_daily_dedicated_reuse_40m.json`、`qwen3_5_9b_saturation_medium_60m.json`、`qwen3_5_9b_sticky_burst_45m.json`、`qwen3_5_9b_enterprise_normal_25m.json`、`qwen3_5_9b_low_reuse_low_frequency_20m.json`、`qwen3_5_9b_quick_daily_8m.json`。
- 新吞吐证明配置：`qwen3_5_9b_saturation_reuse_proof_30m.json`。它把稳定 durable/sticky prefix 作为主体，保留 cold RAG、transient、burst 和 decode-heavy 作为现实扰动，用来复现旧 27B red_burst 中的 SLO goodput 放大机制。
- 新运行脚本：`run_qwen3_5_9b_12h_matrix.sh`、`run_qwen3_5_9b_quick_loop.sh`、`run_remote_qwen3_5_9b_12h_matrix_benchmark.sh`。
- 新单项远程脚本：`run_remote_qwen3_5_9b_saturation_reuse_proof_benchmark.sh`，用于先单独校准高压吞吐目标，再进入完整矩阵。
- summary 脚本已从 27B 专名改成通用标题，并展示 e2e goodput/e2e p95/session/burst 信息。
- 2026-06-29 9B 首轮诊断已经证明：不能直接把 27B mixed saturation 参数平移到 9B。旧 mixed saturation 在 9B 上要么因 admission/scheduler 过强导致 SLO goodput 崩塌，要么 eviction-only 仍显示 high_main 过载。正式矩阵因此把 mixed saturation 降级为可选 guard，主吞吐证明改为 `throughput_reuse_proof_medium`。

当前容量 profile：

| profile | `VLLM_SERVE_GPU_MEMORY_UTILIZATION` | 设计用途 |
|---|---:|---|
| `small` | 0.55 | 容量 sweep 中的较紧容量，不作为唯一主结论 |
| `medium` | 0.70 | 主正式容量，目标是中等/正常容量高压 |
| `large` | 0.85 | 宽松容量对照，证明收益收敛且不劣化 |

主 12h 矩阵预计用时约 9.6h 的纯 workload 时间，加上模型重启和总结开销后约 11-12h：

| 模块 | 容量 | policy | 单 policy 时长 | 纯 workload 时间 |
|---|---|---|---:|---:|
| throughput_reuse_proof | medium | lru, shared_aware | 30min | 60min |
| capacity_sweep | small/medium/large | lru, shared_aware | 6min | 36min |
| daily_dedicated_reuse | medium/large | lru, shared_aware | 40min | 160min |
| mixed_saturation_guard | medium | lru, shared_aware | 60min | 可选 120min |
| sticky_burst | medium | lru, shared_aware | 45min | 90min |
| enterprise_normal | medium | lru, shared_aware | 25min | 50min |
| low_reuse_low_frequency | large | lru, shared_aware | 20min | 40min |

常用命令：

```bash
# 部署到 robowalker 后启动完整 9B 12h 矩阵
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh

# 在远程仓库目录内直接跑完整矩阵
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh

# 30 分钟左右的调参 quick loop，默认 medium + small，policy 为 lru/shared_aware
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh

# 只跑单个容量 quick loop
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh medium
```

## 核心判断

可以提高或放宽 KV cache 容量，但不能只改文字。正式表述应该从“KV cache 紧张”升级为“中等容量下的高压服务场景”，前提是每次 run 都用指标证明容量确实处在中等区间。

推荐结论表述改为：

> 在 Qwen3.5-9B、2 x RTX 3090 24GB、可调 KV cache 容量的服务场景中，KVFabric 通过生命周期感知的驱逐、admission control 与 hint-aware scheduler，降低有价值 prefix block 被错误驱逐后的 rebuild；在中等容量和高压负载下提升 SLO goodput；在多轮/长文档等可复用子场景中争取端到端延迟改善；在普通企业混合流量与低复用低频流量中保持不劣化。

不建议继续使用下面这种表述：

- “所有场景吞吐提升 30%。”
- “只要有 prefix cache 就一定降低延迟。”
- “KVFabric 在低压场景也一定有收益。”
- “KV cache 命中率低说明场景不真实。”

更准确的说法是：KVFabric 优化的是“有价值 KV block 在容量有限时的生命周期管理”。当容量过大、请求低频、prefix 完全不复用时，最优结果应是低开销、低干预、不劣化；当容量中等、负载高、存在稳定共享前缀时，才应出现明显收益。

### 性能目标优先级

主实验必须优先回答两个性能问题：

1. 高压吞吐：在 `kv_medium` 容量、高并发、有稳定复用前缀的 saturation 场景中，shared_aware/full policy 的 SLO goodput 是否比 LRU 明显提高。主目标是 +30% 以上。
2. 合适场景延迟：在 daily_dedicated_reuse 和 sticky_burst 这类高复用、长会话、长文档/agent follow-up 场景中，shared_aware/full policy 是否让 hot reusable requests 的 TTFT/e2e p95 明显降低。主目标是 p95 或 TTFT 降低 30% 以上。

其他测试只服务于这两个目标：

- capacity sweep：证明 30%+ 收益来自容量竞争和生命周期管理，不是单点调参。
- enterprise/low_reuse：证明普通和低复用场景不劣化，但不要求这些场景也提升 30%。
- hint robustness/ablation：只做诊断和补充，不应占主 12h 矩阵的核心时间。

## 外部参考与启发

vLLM 的 automatic prefix caching 是哈希块方案：KV block 由父哈希、block tokens 和额外哈希组成，只缓存完整 block；调度时通过 prompt tokens 查找已计算 block，分配时从 free queue 取 block，遇到已缓存 block 就按 LRU 语义驱逐。参考：[vLLM Automatic Prefix Caching](https://docs.vllm.ai/en/stable/design/prefix_caching/)。

PagedAttention 的核心贡献是把 KV cache 组织成分页块，缓解传统连续 KV 分配的内存碎片和浪费。KVFabric 不应挑战这个基础，而应作为 vLLM block pool 上的生命周期策略层。参考：[Efficient Memory Management for Large Language Model Serving with PagedAttention](https://arxiv.org/abs/2309.06180)。

SGLang 的 RadixAttention 说明多轮、agent、few-shot、树状分支和稳定 prefix 是 prefix cache 最自然的收益区间。KVFabric 的 family/tree 元数据与这一方向一致，但需要避免硬保护导致 cache 污染。参考：[Fast and Expressive LLM Inference with RadixAttention and SGLang](https://www.lmsys.org/blog/2024-01-17-sglang/)。

DistServe 和 Sarathi-Serve 都强调 LLM serving 需要以 goodput、prefill/decode 干扰和延迟 SLO 为核心，而不是只看 raw token/s。KVFabric 的正式指标继续以 SLO goodput 为主是合理的，但 trace 场景必须补上端到端排队延迟。参考：[DistServe](https://arxiv.org/abs/2401.09670)、[Sarathi-Serve](https://arxiv.org/abs/2403.02310)。

H2O 证明 KV/token 的价值并不均匀，保留策略可以基于未来贡献或 heavy-hitter 信号。KVFabric 可以借鉴“价值非均匀”思想，但当前目标是 serving 侧 prefix block 生命周期，而不是模型内部 attention KV 剪枝。参考：[H2O](https://arxiv.org/abs/2306.14048)。

RAGCache、CacheBlend、CacheGen 与 LMCache 说明业界趋势正在从单机 LRU prefix cache 走向知识/片段级、多级、可观测、可迁移的 KV cache 管理。KVFabric 近期不必实现复杂分层缓存，但应把指标和设计预留给 GPU/CPU 分层、知识块复用和跨请求/跨 worker 重用。参考：[RAGCache](https://arxiv.org/abs/2404.12457)、[CacheBlend](https://arxiv.org/abs/2405.16444)、[CacheGen](https://arxiv.org/abs/2310.07240)、[LMCache](https://docs.lmcache.ai/)。

## 当前实验复盘

### 旧 27B 高压阶段 30%+ uplift 的真实来源

之前 saturation 4h/12h 中出现的 35% 甚至 95% 阶段 uplift，主要来自 SLO goodput 的边界放大效应：

- raw total tok/s 只小幅变化。4h saturation 中 shared_aware raw total tok/s 约 +1.70%，12h saturation 中约 +1.73%。
- shared_aware 显著减少错误驱逐后的 rebuild。4h rebuilt-from-eviction 下降约 66.16%，12h 下降约 71.88%。
- 在 red_burst/high_main 阶段，LRU 的一部分请求已经贴近或越过 SLO 边界。shared_aware 减少 rebuild 后，少量 response latency/prefill 成本改善会把这些边界请求重新推回 SLO 内，因此 SLO goodput 的百分比提升远大于 raw throughput。
- 27B 远程脚本当时使用的是 positive/hit-aware scheduler profile，而不是无限 defer。这个 scheduler 能优先调度更可能复用缓存的请求，同时不应长期压住 decode-heavy 或低复用请求。

因此 30%+ 目标必须写成：

> 在高压、SLO 边界、存在稳定可复用 prefix 且有一定 cold churn 的阶段，SLO goodput 提升 30% 以上。

不能写成：

> KVFabric 让所有场景 raw total token/s 提升 30%。

要稳定复现这个机制，实验需要满足三个条件：

1. LRU 不能太轻。如果 LRU p95 远低于 SLO 且 SLO miss 接近 0，shared_aware 即使减少 rebuild，也不会产生 30% SLO goodput 差距。
2. LRU 也不能 redline。如果 LRU 大量 timeout 或持续排队失控，shared_aware 的改善会被队列拥塞淹没，实验会变成过载测试。
3. shared_aware 不能靠无界 defer/admission 牺牲尾延迟。scheduler 必须有 max defer count、age guard、latency-protected class 和 per-class SLO 监控。

### 2026-06-29 9B 首轮诊断

9B 首轮 mixed saturation 不能直接作为正式结果：

- full shared_aware 在旧 mixed saturation 上 goodput 明显低于 LRU，主要原因是 admission/scheduler 组合过强，让大量请求落到 35s SLO 外；raw total tok/s 只小幅下降，但 SLO goodput 被放大成失败。
- eviction-only shared_aware 减少了极端 admission/scheduler 负面影响，但 high_main 仍显示 mixed saturation 对 9B 太苛刻，不适合作为主吞吐证明。
- 这说明 9B 模型、hybrid KV 容量、负载并发和 SLO 边界都发生了变化，需要重新校准 trace。

据此已做三项修正：

1. scheduler 默认增加 defer count/age guard，避免无界推迟请求。
2. duration loadgen 增加 `class_slo_seconds`，让 decode-heavy 这类长输出请求不再被 35s prefill-heavy SLO 错判。
3. duration loadgen 增加 `slo_probe_seconds`，同一轮 run 同时报告 18/20/22/25/30/35s goodput，避免为了选 SLO 反复重跑。
4. 新增 `qwen3_5_9b_saturation_reuse_proof_30m.json`，先用少用户/团队高复用高压场景校准 30%+ SLO goodput，再把普通 mixed saturation 放回可选 guard。

当前 9B reuse-proof LRU 实测显示 high_main p50/p95 约 24/27s，red_burst p50/p95 约 32/34s；35s SLO 下 `goodput == total throughput`，无法产生 SLO goodput 分化。离线按 lifecycle 重算后，20s/22s 对 high_main 过苛刻，而 25s 下 high_main 约 22% miss、red_burst 约 92% miss，更接近“可恢复的高压 SLO 边界”。下一轮主 SLO 因此改为 25s，并保留 18/20/22/25/30/35s probe。这个 SLO 调整按模型大小和硬件速度重新设定服务目标：9B 在 2 x 3090 上本来就应比 27B-FP8 有更紧的响应 SLO。

同一轮 partial shared_aware 显示 full scheduler 在 9B high_main 初期仍可能拖慢 p50/p95，因此下一轮 throughput proof 默认收敛 scheduler：

- `KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP=0`，先关闭 defer。
- `KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW=16`。
- `KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO=0.45`。
- `KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN=6.0`。
- `KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP=2`。

这个调整的原则是先验证 shared-aware eviction/admission 对 SLO goodput 的稳定收益，再把更强 positive/defer scheduler 作为 ablation 逐项打开；不能让 scheduler 的尾延迟风险污染主吞吐证明。

### saturation_throughput

当前 12h 配置是闭环压测，每个 policy 约 4 小时：

- warmup：600s，并发 8，不计分。
- low_guard：1200s，并发 4，低压 guard。
- high_main：11400s，并发 16，主高压段。
- red_burst：1200s，并发 20，红区 burst。

请求池由 3000 轮生成。每轮大致包含：

- durable hot family：9 个，稳定企业工作流/规则/模板 prefix。
- sticky follow-up：5 个，多轮历史增长。
- cold RAG：8 个，一次性长证据段，低复用。
- transient：3 个，短期模板，部分重叠但不应长期保护。
- decode-heavy：每轮 1 个，更偏 decode 而非 prefill reuse。
- burst cold：每 5 轮加 5 个冷 RAG burst。

它主要证明高压力下 shared-aware policy 能减少错误驱逐和 rebuild，并把更多 token 放进 SLO 内。当前代表性 12h 结果：

| policy | goodput tok/s | vs LRU | avg latency | p95 latency | prefix hit token rate | rebuilt |
|---|---:|---:|---:|---:|---:|---:|
| lru | 601.57 | 0.00% | 27.264s | 33.662s | 1.79% | 12680 |
| shared_aware | 675.80 | +12.34% | 26.791s | 33.137s | 2.94% | 3566 |
| family_protect | 572.13 | -4.89% | 27.383s | 34.104s | 0.96% | 3966 |

这组实验有说服力，但“KV cache 紧张”描述过强。更严谨的写法是：高并发、高 cold churn、稳定热 prefix 混合下，cache 容量相对活跃工作集偏紧。下一版应把容量调到中等，并保留压力，让 LRU 仍会发生一定错误驱逐，但不把系统推到异常排队或大量 timeout。

### enterprise_mixed_trace

当前 12h 配置：

- trace profile：`enterprise_mixed`。
- duration：14400s。
- request_rate：0.18，4h 实际约 0.2198 req/s。
- max_model_len：4096。
- max_in_flight：32。
- hint_regime：partial_hints。
- warmup：300s。
- timeout：900s。

请求类型包括 agent_tool_loop、multi_turn_support、RAG hot/cold docs、decode_heavy_report、extraction/classification、tenant workflow hot。

当前 4h 结果说明它更像普通场景/非退化实验：

| policy | total tok/s | avg latency | p95 latency | prefix hit token rate | rebuilt |
|---|---:|---:|---:|---:|---:|
| lru | 437.27 | 8.909s | 22.712s | 13.39% | 757 |
| shared_aware | 437.27 | 9.097s | 23.081s | 8.86% | 358 |
| family_protect | 437.25 | 8.967s | 22.794s | 10.31% | 268 |

这组结果不适合宣称吞吐提升，但适合证明“普通企业混合流量下不明显劣化，并降低 rebuild”。下一版应该加 SLO，例如 45s 或 60s，并要求 e2e latency 与 error 不劣化。

### sticky_conversation_trace

当前 12h 配置：

- trace profile：`conversation_sticky`。
- duration：14400s。
- request_rate：0.62，4h trace 实际生成约 0.7529 req/s。
- max_in_flight：64。
- max_model_len：4096。
- SLO：240s。
- timeout：1500s。
- hint_regime：partial_hints。
- remote launcher 启用 sticky scheduler profile、age guard 与 latency protection。

请求类型包括 deep_multi_turn_chat、long_doc_followup_qa、agent_tool_loop、cold_rag_noise、decode_heavy_noise。

当前最新 4h 结果：

| policy | goodput tok/s | vs LRU | avg latency | p95 latency | prefix hit token rate | rebuilt |
|---|---:|---:|---:|---:|---:|---:|
| lru | 1202.27 | 0.00% | 119.486s | 171.099s | 0.00% | 11555 |
| shared_aware | 1196.51 | -0.48% | 118.492s | 170.369s | 0.44% | 2209 |
| family_protect | 1190.90 | -0.95% | 118.825s | 170.161s | 0.09% | 2224 |

正面信号：

- shared_aware rebuilt-from-eviction 降低约 80.88%。
- overall avg/p95 latency 有小幅改善。
- deep_multi_turn_chat、long_doc_followup_qa、agent_tool_loop 都有小幅改善。

负面信号：

- decode_heavy_noise p95 从 252.472s 上升到 358.073s。
- goodput 没有超过 LRU。
- trace loadgen 记录了 `send_delay`，但当前 SLO pass 使用的是 response latency，不是 `send_delay + response latency`。

因此 sticky 的正式结论不能写成“延迟明显优化”。更严谨的结论是：已有实验显示 hot sticky 类有局部延迟改善趋势，但低复用长输出类可能被 scheduler promotion 拖慢；需要用 latency-protected scheduler、端到端延迟指标和更合理负载重新验证。

## Cache hit 率口径

当前代表性 prefix hit token rate：

| 实验 | LRU | shared_aware | family_protect |
|---|---:|---:|---:|
| saturation 12h | 1.79% | 2.94% | 0.96% |
| saturation 4h | 1.75% | 2.65% | 1.85% |
| enterprise 4h | 13.39% | 8.86% | 10.31% |
| sticky latest 4h | 0.00% | 0.44% | 0.09% |

这些数字不能直接和“日常 AI 使用里 80%-90% 缓存命中”比较，因为口径不同。

日常使用中体感 80%-90% 命中，通常对应的是：

- 单个用户或单个会话内的 eligible prompt tokens 命中率。
- Provider 侧 session sticky、system prompt、工具 schema、长文档、聊天历史的重复前缀。
- 应用层可能复用了同一上下文、同一项目、同一文档、同一 agent 配置。
- 统计口径可能只看“可缓存 token 中有多少命中”，而不是全服务所有 token。
- 用户请求到达频率较低，冷 churn 不强，热上下文不容易被其他租户挤掉。

当前实验的 prefix hit token rate 是全服务、全请求、vLLM exact full-block prefix hit 口径。它会被下面因素拉低：

- saturation 中有大量 cold RAG、burst cold、transient、decode-heavy。
- sticky trace 的多轮 follow-up 如果 prompt 拼接、turn 增长或生成 trace 不形成完全相同的 block prefix，exact prefix hit 会很低。
- 2 x 3090 跑 27B-FP8 时，KV block 预算本身有限；高并发下热 block 容易被冷请求挤掉。
- vLLM 只缓存完整 block，部分 block 或非前缀片段不计入命中。
- shared_aware 的主要收益可能是“少 rebuild”和“少误驱逐”，不一定直接体现为高 overall hit rate。

下一版应增加三种 hit 口径：

1. overall prefix hit token rate：现在已有，继续保留。
2. eligible prefix hit token rate：只统计 durable/hot/sticky/RAG-hot 等理论可复用请求。
3. per-family warm hit rate：family 第 2 次及以后请求的命中率，排除首次冷启动。

如果要模拟日常工作学习科研场景，应该新增 `daily_dedicated_reuse_trace`，让稳定项目/文档/会话占比更高、cold churn 更低、请求频率更低，并报告 eligible hit rate。这个场景中 50%-80% eligible hit 是合理目标；全服务 overall hit 不必强行做到 80%-90%。

### 少用户长会话是真实且重要的场景

需要把“少数用户长期使用同一张卡或同一组卡”作为一等场景。很多真实 AI 使用来自少量长期活跃用户或固定团队，而不是上百个租户不断混合请求：

- 一张卡或一组卡服务少数几个稳定用户。
- 一个用户长期围绕同一项目、同一篇论文、同一个代码库、同一个知识库或同一组 agent 工具工作。
- system prompt、工具 schema、项目说明、文档摘要、聊天历史前缀在几十分钟到数小时内反复出现。
- 用户请求间隔可能是几十秒到数分钟，cache 有机会长时间驻留。
- 偶尔插入新的文档、临时查询、decode-heavy 任务或另一个用户的请求，造成温和 churn。

这种场景下，eligible hit rate 可能显著高于当前 saturation/sticky 压测结果。KVFabric 更可能在温和 churn 下避免少数高价值长上下文被低复用请求挤掉。

需要注意事实边界：

- vLLM prefix cache 只在 server 进程存活期间保留，重启后不保留。
- 命中依赖 exact token prefix。动态时间戳、随机 request id、不断变化的系统提示会破坏命中。
- 如果 cache 足够大且没有背景 churn，LRU 也会表现很好，此时 KVFabric 的合理结果是低开销不劣化。
- KVFabric 的收益应该出现在“高价值长上下文 + 少量背景 churn + 中等容量”的交界处。

因此下一版实验必须加入 `daily_dedicated_reuse_trace`，并把它作为延迟与高命中率证明的主场景之一。

## 中等或正常 KV cache 容量定义

不能用“感觉不紧张”定义容量。建议每次 run 写入 `capacity_profile.json`，包含：

- `kv_block_total_avg/p50/p95`。
- `kv_block_free_avg/p50/p95`。
- `active_block_peak_ratio`：活跃请求占用 block 峰值 / total blocks。
- `cached_block_resident_ratio`：可复用 cached blocks / total blocks。
- `evictions_per_1k_requests`。
- `rebuilt_from_eviction_per_1M_prompt_tokens`。
- `send_delay_p95_seconds`。
- `num_requests_waiting_p95`。
- `timeout_rate`。

建议容量分档：

| 档位 | 定义 | 用途 |
|---|---|---|
| roomy | active peak < 50%，eviction 很少，send_delay p95 接近 0 | 证明收益自然消失且 overhead 小 |
| normal/medium | active peak 55%-80%，有可观 eviction/rebuild，但 send_delay p95 可控，无持续 timeout | 主正式实验 |
| stress | active peak 80%-95%，eviction/rebuild 明显，waiting 增长但仍稳定 | 高压收益实验 |
| redline | active peak > 95% 或 send_delay 长时间累积，timeout/error 明显 | 只做边界压力，不作为主结论 |

用户希望“提高 KV cache 容量、把描述改为中等或正常”是合理方向，但实现上应优先通过以下方式达到中等容量：

1. 降低冷 churn 和 red burst 比例，而不是让 GPU OOM 风险上升。
2. 将 sticky 的 `request_rate` 和 `max_in_flight` 调到 send_delay 可控。
3. 保持 `max_model_len=4096`，不要为了制造收益把上下文长度推到不常见极端。
4. 如果远程 vLLM 启动稳定，可以小幅提高 `gpu_memory_utilization`，例如从 0.90 校准到 0.92/0.94，但必须先跑 smoke，确认无 OOM 和无显存碎片异常。
5. 如果 vLLM 0.22.1 环境支持 KV cache dtype 或相关压缩选项，可以作为独立 capacity sweep，不混入主对比。
6. 不建议直接用 `num_gpu_blocks_override` 假装增加容量；override 应只用于复现实验，不应用于正式性能结论，除非有 profile 证明它安全。

正式写法应是：

- “中等容量高压”：容量指标落在 normal/medium，负载高但无长时间排队失控。
- “stress high pressure”：容量指标落在 stress，用于证明极限收益。
- “low-reuse low-frequency”：容量 roomy 或 medium，证明不劣化。

## 模型与容量决策：Qwen3.5-9B + 可调 KV

### 结论

按新的时间约束和模型要求，主线改为 `Qwen/Qwen3.5-9B`，profile 名建议 `qwen3_5_9b`。旧 27B-FP8 结果只作为历史压力参考，不再作为新矩阵的主结果；8B/14B 方案暂时移出主设计。

`Qwen/Qwen3.5-9B` 模型卡说明语言模型约 9B 参数，支持 vLLM，并采用 Gated DeltaNet 与 Gated Attention 混合结构。参考：[Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)。这个模型对 KVFabric 有两个好处：

- 比 27B-FP8 轻，能给 KV cache 留出更可调的容量空间。
- 仍是 9B 级服务模型，不会像很小模型那样把 serving 压力完全稀释。

关键设计变化：

1. KV cache 容量本身成为实验变量，而不是默认把 GPU 显存尽量占满。
2. 完整一轮实验限制在约 12h，主要包含高压吞吐、合适场景延迟、capacity sweep、普通场景不劣化和低复用不劣化。
3. 调参 run 控制在 1-3h，便于 3-4 天内多次试错。

### KV cache 粗算

Qwen3.5-9B 是 hybrid 架构，不能简单套用普通 dense Transformer 的“每层都有 attention KV”公式。粗略边界如下：

```text
attention_kv_lower_bound =
  gated_attention_layers * num_kv_heads * head_dim * 2(K,V) * dtype_bytes

all_attention_upper_bound =
  total_layers * num_kv_heads * head_dim * 2(K,V) * dtype_bytes
```

按模型卡给出的 32 层、hybrid layer layout、4 KV heads、head dim 256 粗算：

| 口径 | 估计 | KV bytes/token | 16-token block |
|---|---|---:|---:|
| 仅 gated attention 层下界 | 8 attention layers | 32 KiB | 0.50 MiB |
| 假设全部 32 层都有 attention 的上界 | 32 layers | 128 KiB | 2.00 MiB |
| vLLM 实际状态缓存 | KV + hybrid state，以实测为准 | 以实测为准 | 以实测为准 |

因此正式容量必须以 vLLM 启动日志的 `GPU KV cache size` 和 Prometheus/lifecycle 指标为准。不要只用公式判断。

### 可调容量 profile

`serve_local.sh` 已支持 `VLLM_SERVE_GPU_MEMORY_UTILIZATION` 覆盖 profile 中的 `GPU_MEMORY_UTILIZATION`。这正好可以把 KV cache 容量做成实验变量。

建议新增基础 profile：

```bash
MODEL_PRESET=qwen3_5_9b
MODEL_ID=Qwen/Qwen3.5-9B
MODEL_DIR_NAME=Qwen3.5-9B
SERVED_MODEL_NAME=qwen3.5-9b-local
MAX_MODEL_LEN=4096
GPU_MEMORY_UTILIZATION=0.70
MAX_NUM_SEQS=64
TENSOR_PARALLEL_SIZE=2
DTYPE=auto
LANGUAGE_MODEL_ONLY=1
ENABLE_PREFIX_CACHING=1
```

容量 profile 不通过换模型实现，而通过启动参数控制：

| profile | `VLLM_SERVE_GPU_MEMORY_UTILIZATION` | `MAX_MODEL_LEN` | 目的 | 预期 |
|---|---:|---:|---|---|
| `kv_small` | 0.55 | 4096 | 约束 KV 容量，模拟较紧但非极端的服务部署 | LRU 有明显 eviction/rebuild |
| `kv_medium` | 0.70 | 4096 | 主正式容量，接近“中等/一般容量” | 有竞争但 send_delay 可控 |
| `kv_large` | 0.85 或 0.90 | 4096 | 大容量/宽松对照 | 收益应自然收敛，不劣化 |

注意：

- `MAX_NUM_SEQS`、concurrency、request_rate 调的是负载压力，不等价于物理 KV 容量。
- capacity sweep 时应尽量固定 workload，只改 `VLLM_SERVE_GPU_MEMORY_UTILIZATION`，否则容量变量会和负载变量混在一起。
- 如果 `kv_small=0.55` 启动失败或可服务容量太小，可改为 0.60。
- 如果 `kv_large=0.90` 不稳定，可用 0.85。
- 每次 run 必须记录实际 `GPU KV cache size`，并写入 summary。

## 改进后的实验矩阵

### 模型维度

新矩阵只围绕一个主模型：

- 模型：`Qwen/Qwen3.5-9B`。
- 硬件：2 x RTX 3090 24GB。
- 容量：`kv_small / kv_medium / kv_large`。
- 主 policy：`lru`、`shared_aware`。
- 扩展 policy：`soft_family_budget` 或当前可用的 `family_protect`，只在 saturation 和 daily_dedicated_reuse 中作为候选策略跑。

### A. daily_dedicated_reuse_trace

目标：模拟一张卡或一组卡服务少数稳定用户的真实日常使用，证明高价值上下文可以长期驻留，KVFabric 在温和 churn 下减少热上下文误驱逐，并改善可复用请求的 TTFT/e2e latency。

建议参数：

| 项 | 建议 |
|---|---|
| user_count | 2-6 |
| tenant_count | 1-3 |
| project/session_count | 4-12 |
| capacity | `kv_medium` 主线，附加 `kv_large` 对照 |
| request_rate | 0.20 / 0.35 / 0.50 smoke 后选 |
| max_in_flight | 8-16 |
| SLO | e2e 15s 或 30s，按 smoke p95 校准 |
| stable project/doc/code context | 60%-75% |
| agent/tool follow-up | 10%-15% |
| cold/background query | 5%-10% |
| decode-heavy/background writing | 3%-5%，latency protected |
| session lifetime | 30-120min，完整 12h 跑里可加速到 20-60min |
| follow-up interval | 20-180s，加速 trace 可按比例压缩 |

这个场景不应该用很高并发硬压。它的关键是“同一用户/项目上下文能否被保住”，而不是把 GPU 打满。为了在短时间内获得足够样本，可以压缩真实时间间隔，但要保持会话局部性和长尾间隔。

验收：

- eligible prefix hit token rate 目标 50%-80%。
- warm-family hit rate 目标 70%-90%，至少明显高于全服务 overall hit。
- shared_aware 对 hot project/doc/code family 的 rebuilt-from-eviction 低于 LRU 50%。
- hot reusable classes 的 TTFT 或 e2e p95 相比 LRU 降低 30% 以上，这是该场景的主要性能目标。
- 如果 `kv_large` 下 LRU 已经接近最优，允许收益收敛；但 `kv_medium` 必须争取 30%+ 延迟改善或清楚证明瓶颈不在 KV 生命周期。
- cold/background/decode-heavy p95 不差于 LRU 5%-10%。

### B. saturation_medium_pressure

目标：主吞吐证明实验。证明中等 KV 容量、高压、有稳定 prefix 复用时，shared_aware/full policy 提升 SLO goodput。

建议参数：

| 项 | `kv_small` | `kv_medium` 主线 | `kv_large` |
|---|---:|---:|---:|
| warmup | 3-5min c=16 | 3-5min c=20 | 3-5min c=24 |
| low_guard | 5min c=12 | 5min c=16 | 5min c=20 |
| high_main | c=32/40 smoke 后选 | c=48/56 smoke 后选 | c=64/80 smoke 后选 |
| red_burst | c=48，只作 stress | c=72，只作 stress | c=96，只作 stress |
| cold_rag_per_round | 6-8 | 6-8 | 8-10 |
| burst_cold_requests | 3-4 | 4-5 | 5-6 |
| hot_family_per_round | 10-12 | 10-12 | 12-14 |
| sticky_followup_per_round | 6-8 | 6-8 | 8-10 |
| transient_per_round | 2-3 | 3 | 3-4 |
| SLO | smoke 校准，建议 10-20s | smoke 校准，建议 10-20s | smoke 校准，建议 8-15s |

验收：

- high_main shared_aware/full policy SLO goodput >= LRU +30%，这是高压吞吐主目标。
- red_burst 可展示更大收益，但不能作为唯一主结论。
- shared_aware rebuilt-from-eviction <= LRU 的 50%。
- avg/p95 response latency 不差于 LRU 5% 以上。
- e2e latency 在闭环场景可选；如果未来改为开环，也必须报告 e2e。

### C. capacity_sweep

目标：验证收益是否随容量变化合理衰减，排除只适配“极小 cache”的情况。

建议三个容量点固定同一 workload，只改变 `VLLM_SERVE_GPU_MEMORY_UTILIZATION`：

| profile | GPU memory util | 固定 workload | 预期 |
|---|---:|---|---|
| `kv_large` | 0.85/0.90 | c=48 或 trace rate 固定 | LRU 已足够好，KVFabric overhead < 3% |
| `kv_medium` | 0.70 | 同上 | shared_aware 收益最有说服力 |
| `kv_small` | 0.55/0.60 | 同上 | 收益更大，但不应 redline |

每个 profile 只跑 LRU + shared_aware。完整 12h 矩阵中每个组合 6min，只做容量曲线的 sanity check；单独调参时每个组合 8-10min 即可。

验收：

- `kv_large` 不劣化。
- medium 明显提升。
- `kv_small` 提升更大但不出现错误率异常。
- 收益曲线符合直觉：large 小，medium/small 大。

### D. enterprise_mixed_normal

目标：普通企业服务不退化。

建议参数：

| 项 | 建议 |
|---|---|
| capacity | `kv_medium`，可附加 `kv_large` 对照 |
| request_rate | 0.80 / 1.00 / 1.20 smoke 后选 |
| max_in_flight | 64 |
| SLO | e2e 20s 或 30s，按 smoke p95 校准 |
| warmup | 180s |
| hint_regime | partial_hints，12h 完整跑里加 no_hints mini |

验收：

- total tok/s 与 goodput 不低于 LRU 3% 以上。
- avg/p95/e2e p95 不差于 LRU 5% 以上。
- rebuilt-from-eviction 显著低于 LRU。
- error/timeout 不高于 LRU。
- no_hints 下不劣化，partial_hints 下 lifecycle 指标更好。

### E. sticky_burst_trace

目标：在 dedicated daily 的基础上增加多轮 agent、长文档 follow-up 和短 burst，检验 scheduler 是否能在更复杂的 sticky 流量中保护 decode-heavy/low-reuse 请求。

它不是主日常场景，不应再像旧 sticky_conversation 那样压到巨大排队。新版应保持 send_delay 可控。

建议参数：

| 项 | 建议 |
|---|---|
| capacity | `kv_medium` 主线，必要时加 `kv_small` mini |
| request_rate | 0.40 / 0.60 / 0.80 smoke 后选 |
| max_in_flight | 32-48 |
| SLO | e2e 30s 或 45s，按 send_delay p95 校准 |
| cold_rag_noise | 5%-8% |
| decode_heavy_noise | 3%-5%，必须 latency protected |
| session_count | 比当前 sticky 少，让每个 session 更深 |
| follow-up interval | 10-180s，保持长尾 |
| long_doc | 每个文档至少 4-8 次 follow-up |

验收：

- eligible prefix hit token rate 明显高于当前 sticky，目标 30%-60%；per-family warm hit 可更高。
- deep_multi_turn_chat、long_doc_followup_qa、agent_tool_loop 至少两个类别 e2e p95 降低 >= 30%。
- decode_heavy_noise 与 cold_rag_noise p95 不差于 LRU 5%-10% 以上。
- shared_aware/full policy goodput 不低于 LRU；如果该 sticky burst 子场景用于吞吐展示，目标同样按 +30% 看。
- `send_delay_p95_seconds <= 30s`，否则该 run 不用于延迟结论。

### F. low_reuse_low_frequency

目标：证明低复用、低频、普通容量下不会劣化。

建议参数：

- capacity：`kv_large` 或 `kv_medium`，优先 `kv_large` 证明宽容量普通场景不劣化。
- request_rate：0.30-0.60。
- max_in_flight：32-48。
- cold/extraction/decode-heavy 占 80%-90%。
- durable hot family 不超过 10%-15%。
- SLO：e2e 30s 或 45s。
- hint_regime：no_hints + partial_hints。

验收：

- total tok/s/goodput 不差于 LRU 3%。
- avg/p95/e2e p95 不差于 LRU 5%。
- scheduler defers/promotes 接近 0 或很低。
- admission limited 对 low reuse 生效，但不影响用户可见延迟。

### G. 可选：hint robustness

目标：证明 hint-aware 不是作弊；hint 有帮助，但错 hint 或缺 hint 不应导致灾难。

这个测试不放进主 12h 性能矩阵。只有在主结果被质疑“全靠完美 hint”或策略行为异常时再补跑。

四档：

- no_hints：只靠实际 prefix/lifecycle。
- partial_hints：当前默认。
- noisy_hints：10%-20% hint 错误或缺失。
- full_hints：理想上限，不作为主结果。

验收：

- no_hints 不明显劣化。
- partial_hints 优于 no_hints。
- noisy_hints 不出现明显劣化或 starvation。
- full_hints 只作为上界分析。

### H. 可选：policy ablation

目标：把收益归因拆开，避免“所有机制一起开，不知道谁有效”。

这个测试不放进主 12h 性能矩阵。只有在 shared_aware/full policy 达到性能目标后，才用它解释收益来源；如果主性能目标没达成，优先调场景和策略，不先跑长 ablation。

建议 policy：

- lru：原始基线。
- eviction_only：只启用 retain score/ranked eviction。
- admission_only：只启用 admission control。
- scheduler_only：只启用 positive/defer/latency protection。
- full_shared_aware：三者都启用。
- soft_family_budget：替代当前 family_protect。

验收：

- saturation 中 eviction/admission 是主要 goodput 来源。
- sticky_burst 中 scheduler latency protection 负责保护 decode-heavy，daily_dedicated_reuse 中 scheduler 不应破坏少用户长会话延迟。
- soft_family_budget 不能再出现 family_protect 过保护导致吞吐差于 LRU 的问题。

## 指标与日志改造设计

### 端到端延迟

`experiments/long_pressure_benchmark/examples/online_trace_loadgen.py` 当前在 `record_success` 中使用 `latency <= slo_seconds` 判断 SLO。这个 latency 是 HTTP POST 后的响应时间，不包含 semaphore 等待和 trace scheduled arrival 之后的排队延迟。脚本已经记录 `send_delay`，因此应新增：

- `e2e_latency_seconds = send_delay_seconds + latency_seconds`。
- `e2e_latency_avg/p50/p95/p99`。
- `e2e_slo_pass/miss/miss_rate`。
- `e2e_goodput_total_tokens_per_second`。
- per-class e2e latency 和 e2e goodput。

正式 trace 结论必须同时报告：

- response latency：服务端接受请求后的响应性能。
- e2e latency：从 trace 计划到达到完成的用户体感性能。

如果 response latency 改善但 e2e latency 恶化，不能宣称用户延迟优化。

### Cache hit 新口径

新增：

- `overall_prefix_hit_token_rate`：现有口径。
- `eligible_prefix_hit_token_rate`：只统计 durable/sticky/rag_hot/agent 等可复用请求。
- `warm_family_prefix_hit_token_rate`：family 第 2 次及以后。
- `cold_first_touch_tokens`：首次出现不可命中的 token。
- `rebuild_avoided_tokens`：估算被策略避免的重算 token。
- `hit_tokens_by_request_class`。
- `hit_tokens_by_hint_expected_reuse`。

### 容量与压力

新增每 30s 采样：

- total KV blocks、free KV blocks、cached KV blocks、active KV blocks。
- active/cached/free ratio。
- eviction rate、rebuild rate、admission limited rate。
- running/waiting requests。
- prefill tokens/s、decode tokens/s。
- prefix hit queries/hits/tokens。
- per-policy capacity profile summary。

### Scheduler fairness

新增：

- `request_age_at_schedule_ms`。
- `promotion_delay_ms`。
- `defer_delay_ms`。
- `promotions_by_class`。
- `defers_by_class`。
- `latency_protected_promotions_by_class`。
- `head_age_guard_skips_by_class`。
- `max_consecutive_promotions`。
- `per_class_slo_miss_rate`。

这些指标用于证明 positive promotion 没有长期压住 decode-heavy 或 cold noise。

## 代码算法改进设计

### 1. 从 hard family_protect 改成 soft family budget

当前 `family_protect` 在 `_rank_key` 中把 protected block 放进硬 bucket。问题是 protected 一旦过多，会把冷/旧 family 长期留在 cache，压低整体吞吐。

建议改为：

- 每个 family 有预算：`family_budget_blocks = min(base + alpha * recent_hits, max_family_share * total_blocks)`。
- 超预算的 family block 不再硬保护，只保留 retain score。
- family 保护随时间衰减：最近 N 分钟无命中则降低 family value。
- regret 可以短期 rescue，但也要过期。
- 热 family 的根部/浅层 prefix 优先，深层分支只有最近命中才保护。

预期效果：

- 保留 family_protect 降 rebuild 的优点。
- 避免当前 12h saturation 中 family_protect goodput -4.89% 的过保护问题。

### 2. 引入 TinyLFU/ARC 思路的 admission

当前 admission 基本是压力阈值 + hint + hit tokens。下一步建议改成轻量级 TinyLFU 风格：

- 用 Count-Min Sketch 或 aging counter 记录 block hash/family 的近似频率。
- 新 block 进入 cache 前与待驱逐 block 比较价值。
- 低频 cold block 即使 prompt 很长，也不一定进入 cache。
- 最近刚命中过的 block 保留 recency bonus，避免纯频率导致老热点占位。

评分建议：

```text
retain_score =
  w_recency * recency_score
+ w_freq * log1p(recent_family_hits)
+ w_share * share_degree
+ w_depth * shallow_prefix_bonus
+ w_regret * recent_rebuild_regret
+ w_cost * estimated_rebuild_tokens
+ w_hint * hint_reuse_bonus
- w_size * block_count_pressure
- w_stale * idle_decay
```

admission 决策：

```text
admit if new_block_score >= victim_score + admission_margin
or request is durable and family is under budget
or block is shallow shared prefix
```

### 3. 自适应压力控制

当前阈值多来自环境变量。建议新增 controller：

- 输入：free ratio、eviction risk、recent rebuild rate、recent prefix hit rate、send_delay p95、per-class SLO miss。
- 输出：admission aggressiveness、promotion aggressiveness、defer aggressiveness。
- 规则：当 e2e/SLO 开始恶化时，优先降低 scheduler promotion，而不是继续保护 cache。

初始可以用分段规则，不必上 ML：

| 状态 | 行为 |
|---|---|
| GREEN | admission 宽松，scheduler 不扫描 |
| YELLOW | 限制低复用 cold miss admission，轻量 positive |
| RED | aggressive admission，positive 仅限高置信 hot/sticky |
| LATENCY_RED | 关闭普通 positive，启用 latency-protected promotion |

### 4. Scheduler 改为 bounded two-lane

当前 scheduler 已有 positive scan、defer、latency protection、head-age guard，但 sticky latest 仍出现 decode_heavy_noise 被拖慢。

建议改成 bounded two-lane：

- lane A：reuse-positive 请求，适合 durable/hot/sticky。
- lane B：latency-protected 请求，适合 decode-heavy、low-reuse、SLO 紧请求。
- 每 K 次 positive promotion 后必须调度一个 head/latency-protected 请求。
- 对每个 request class 设置最大 promotion bypass 次数。
- e2e age guard 使用 trace due time，而不是只用进入 vLLM waiting queue 的时间。
- 当 `send_delay_p95` 或 class SLO miss 上升时，降低 positive scan window。
- 对带 `x-kvfabric-slo-ms` 的请求启用 SLO-aware guard：如果队首请求年龄超过 `SLO * ratio`，positive promotion 不能继续绕过它；如果非队首请求已经接近 SLO，可以进入 latency-protected lane。

目标是在 cache hit 和用户可见延迟之间做有界权衡。

2026-06-29 已先落地轻量版 SLO-aware scheduler guard：

- `KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_RATIO`，默认 0.65。
- `KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_MIN_MS`，默认 3000。
- `KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO`，默认 0.85。
- `KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_MIN_MS`，默认 5000。

这不是新 admission 策略，不会增加 cache 保护强度；它只限制 scheduler 在请求接近 SLO 时继续做复用优先调度。

### 5. 未来复用预测

当前 hint 是显式 header。下一步可加入在线预测，仍保持简单可解释：

特征：

- request_class。
- tenant_id/family_id/session_id。
- family_recent_hits。
- family_interarrival_ms。
- turn_index。
- prompt_tokens。
- previous_rebuild_regret。
- expected_reuse/cache_priority hint。
- last_hit_tokens。

输出：

- `predicted_reuse_probability`。
- `predicted_reuse_tokens`。
- `ttl_seconds`。

先用规则模型，后续再考虑 logistic regression 或 GBDT。不要在正式主实验中引入不可解释模型，避免评审质疑过拟合。

### 6. 分层 KV cache 预留

短期不建议把 LMCache/CacheGen 类分层缓存直接塞进主实验，否则变量太多。建议先预留接口：

- GPU resident cache：当前 KVFabric 管理。
- CPU/offload cache：只做可选实验。
- persistent family cache：只对稳定 system/tool/doc prefix 做长期缓存。
- SERDE/compression：独立 ablation。

主论文/报告先证明单机 GPU KV 生命周期策略有效，再把分层缓存作为未来工作或扩展实验。

## 时长与迭代节奏

### 原则

现在只有 3-4 天做反复试错，因此完整一轮必须压到约 12h。12h run 的目标是在一天内同时拿到：

- 容量敏感性：`kv_small/kv_medium/kv_large`。
- 高压吞吐：saturation goodput。
- 延迟优化：daily dedicated 和 sticky burst 的 TTFT/e2e latency。
- 普通场景：enterprise normal 不劣化。
- 低复用低频：low reuse 不劣化。

主 12h 不再包含 hint robustness 和 ablation。它们是补充诊断，不是性能目标本身。

每次完整 run 后应能决定下一轮调什么，而不是只得到单一场景结果。

### 0.5-1h smoke

只用于确认模型和容量 profile 可启动。

| 步骤 | 时长 | 内容 |
|---|---:|---|
| server smoke | 10-15min | `qwen3_5_9b` 启动、verify、记录 `GPU KV cache size` |
| kv_small mini | 10min | LRU，检查是否 redline |
| kv_medium mini | 10min | LRU，检查 active peak / eviction |
| shared mini | 10min | kv_medium + shared_aware，确认 lifecycle 日志 |

通过条件：

- 三档容量至少 `kv_medium` 和 `kv_large` 能稳定启动。
- `kv_small` 如果 OOM 或 active peak 长期 >95%，改成 0.60。
- `kv_medium` 的 send_delay p95 不应持续累积。

### 1-1.5h 快速调参 loop

目标：快速调并发、request_rate、SLO 和 cold/hot 比例。

| 实验 | policy | 时长 | 目的 |
|---|---|---:|---|
| dedicated daily quick | lru/shared_aware | 15min x 2 | 看 eligible hit、热上下文驻留和 TTFT/e2e |
| saturation quick | lru/shared_aware | 12min x 2 | 看 goodput 与 rebuild 信号 |
| enterprise quick | lru/shared_aware | 8min x 2 | 看普通场景是否劣化 |

总 run 时间约 80min，加启动/summary 约 1.5h。

用于每次小改后的回归，例如：

- `VLLM_SERVE_GPU_MEMORY_UTILIZATION`。
- saturation concurrency。
- sticky request_rate/max_in_flight。
- SLO seconds。
- scheduler positive/defer/latency protection 阈值。
- admission risk threshold。

### 2-3h mini matrix

目标：在进入 12h 完整跑之前，确认容量曲线方向正确。

| 实验 | capacity | policy | 单组合时长 | run 时间 |
|---|---|---|---:|---:|
| daily dedicated mini | medium/large | lru/shared_aware | 15min | 1h |
| capacity sweep mini | small/medium/large | lru/shared_aware | 8min | 48min |
| saturation medium mini | medium | lru/shared_aware/soft_or_family | 15min | 45min |
| sticky burst mini | medium | lru/shared_aware | 12min | 24min |

总 run 时间约 2h57min，加 overhead 约 3h。

进入 12h 完整跑的条件：

- daily dedicated 的 eligible hit rate 明显高于 overall hit。
- `kv_large` 下 shared_aware 不劣化。
- `kv_medium` 或 `kv_small` 下 rebuilt-from-eviction 有明显下降。
- sticky/decode-heavy/cold_noise 没有明显被拖慢。
- send_delay p95 不持续上升。

### 12h 完整矩阵

这是建议的“一次完整跑”。多个实验共同压进约 12h 总预算。

| 模块 | capacity | policy | 单组合时长 | run 时间 | 目的 |
|---|---|---|---:|---:|---|
| throughput_reuse_proof | medium | lru/shared_aware | 30min | 1.0h | 30%+ 高压 SLO goodput 主信号 |
| capacity_sweep | small/medium/large | lru/shared_aware | 6min | 0.6h | 最小容量敏感性 |
| daily_dedicated_reuse | medium/large | lru/shared_aware | 40min | 2.7h | 30%+ 延迟优化主信号 |
| sticky_burst | medium | lru/shared_aware | 45min | 1.5h | 复杂多轮/agent 延迟强化信号 |
| enterprise_normal | medium | lru/shared_aware | 25min | 0.8h | 普通场景不劣化 |
| low_reuse_low_freq | large | lru/shared_aware | 20min | 0.7h | 低复用低频不劣化 |
| mixed_saturation_guard | medium | lru/shared_aware | 60min | 可选 2.0h | 防止主吞吐 trace 过度迎合 |

总 run 时间约 10.6h。加 server restart、summary、sync、dashboard 读取等 overhead，按 12h 预算。

执行细节：

- `family_protect` 不进入默认 12h 主矩阵；soft family budget 作为后续候选策略，只在 shared_aware 达标后补跑解释性 ablation。
- 12h 完整跑只保留一个主模型 `qwen3_5_9b`，不跑 8B/14B。
- capacity_sweep 中 workload 固定，只改 `VLLM_SERVE_GPU_MEMORY_UTILIZATION`。
- throughput_reuse_proof 是高压 goodput 主证明；daily dedicated 是延迟和高命中证明的主场景；enterprise/low_reuse 是不劣化证明。
- mixed_saturation_guard 默认不跑，只有当主结果被质疑“过度迎合少用户高复用”时再加。
- 主结论优先看 `kv_medium`，`kv_small` 用来说明压力边界，`kv_large` 用来说明不劣化/收益收敛。
- hint robustness 和 ablation 不进入主 12h。主结果异常时才补跑；主结果达标后可用作解释性补充。

### 3-4天试错安排

推荐节奏：

| 天数 | 任务 | 预算 |
|---|---|---:|
| Day 1 上午 | 模型下载、profile、smoke、容量初测 | 1-3h benchmark，不含下载 |
| Day 1 下午 | 1-1.5h quick loop 跑 2-3 轮 | 3-5h |
| Day 2 | 2-3h mini matrix 跑 1-2 轮 | 3-6h |
| Day 3 | 12h 完整矩阵 v1 | 12h |
| Day 4 | 根据 v1 结果修参数，再跑 quick/mini 或完整矩阵 v2 | 3-12h |

如果时间只够一次完整 run，应优先保证：

1. saturation_medium。
2. daily_dedicated_reuse。
3. sticky_burst。
4. capacity_sweep。
5. enterprise_normal。
6. low_reuse_low_freq。

hint robustness 和 ablation 只作为可选补跑，不占这一次完整 run 的主预算。

## 验收标准

### 少用户长会话

daily_dedicated_reuse 是最贴近日常 AI 使用的场景。它不要求系统高压满载，而要求证明高价值上下文能长时间驻留。

必须同时报告：

- overall prefix hit token rate。
- eligible prefix hit token rate。
- warm-family hit rate。
- hot family eviction/rebuild count。
- TTFT/e2e avg/p95。
- per-user/per-session hit 和 latency。

成功标准：

- eligible prefix hit token rate 目标 50%-80%。
- warm-family hit rate 目标 70%-90%。
- `kv_medium` 下 shared_aware hot family rebuild <= LRU 的 50%。
- `kv_medium` 下 hot reusable classes 的 TTFT 或 e2e p95 比 LRU 低 30% 以上。
- `kv_large` 下 shared_aware 不劣化，收益自然收敛可以接受。

### 高压吞吐

必须同时满足：

- saturation_medium high_main shared_aware/full policy SLO goodput >= LRU +30%。
- rebuilt-from-eviction <= LRU 50%。
- response p95 不差于 LRU 5%。
- error/timeout 不高于 LRU。
- capacity profile 是 medium 或 stress，不是 redline。

### 延迟优化

只在满足下面条件时宣称：

- 使用 e2e latency，而不是只用 response latency。
- daily_dedicated_reuse 或 sticky_burst 中 deep_multi_turn_chat/long_doc_followup_qa/agent_tool_loop 至少两个类别 TTFT 或 e2e p95 降低 >= 30%。
- decode_heavy_noise/cold_rag_noise e2e p95 不差于 LRU 5%-10%。
- send_delay p95 不超过 30s；超过则该 run 只能算过载实验，不能用于用户延迟结论。

### 普通场景不劣化

enterprise_mixed_normal：

- total tok/s 或 goodput 差距在 -3% 以内。
- avg/p95/e2e p95 差距在 -5% 以内。
- errors/timeouts 不增加。
- rebuild 明显下降。

### 低复用低频不劣化

- total tok/s/goodput 差距在 -3% 以内。
- avg/p95/e2e p95 差距在 -5% 以内。
- scheduler promotion/defer 接近 0。
- admission 不应制造额外排队。

### 通用性

必须展示：

- capacity sweep：`kv_large/kv_medium/kv_small` 收益曲线合理。
- dedicated daily：少用户、长会话、高 eligible hit 的真实日常场景。
- enterprise/low_reuse：普通和低复用场景不劣化。
- per-class：不能只看 overall，必须看 hot、cold、decode-heavy。

可选补充：

- hint robustness：no/partial/noisy/full 不会证明只靠理想 hint。
- ablation：收益来源可解释。

## 风险与反驳准备

质疑：实验过度迎合高压 KV cache。

回应：新增 daily_dedicated_reuse、capacity sweep、enterprise normal、low-reuse low-frequency。主收益不只来自极限高压；少用户长会话验证高命中和热上下文驻留，saturation 只负责高压 goodput。

质疑：cache hit rate 只有几个百分点，不像真实使用。

回应：当前旧数字是全服务 exact full-block prefix hit。新增 daily_dedicated_reuse、eligible hit 和 warm family hit，区分日常会话内命中与混合服务整体命中。

质疑：延迟优化不明显。

回应：当前旧 sticky 结果过载较强，只能说明 rebuild 降低和局部 hot class 小幅改善。正式延迟结论改由 daily_dedicated_reuse 和降压后的 sticky_burst 给出，并必须使用 e2e latency。

质疑：少用户长会话太有利于 cache。

回应：这是现实中的重要部署形态，不是作弊。设计中仍保留温和 background churn、capacity sweep、enterprise normal 和 low-reuse 场景，避免只证明“无竞争时 LRU 也很好”。

质疑：family_protect 失败说明 family/tree 思路无效。

回应：失败点是 hard protect 过保护，不是 family 元数据无效。下一版用 soft family budget 和 decay。

质疑：hint-aware 是作弊。

回应：企业系统本来有 tenant/session/class/SLO metadata；同时新增 no_hints/noisy_hints，证明没有完美 hint 也不会崩。

## 实施路线

### Phase 0：指标修正

- trace loadgen 增加 e2e latency/e2e SLO/e2e goodput。
- summary 增加 eligible hit、warm family hit、capacity profile。
- dashboard 增加 capacity profile 和 e2e 曲线。

### Phase 1：实验校准

- 新增并验证 `qwen3_5_9b` profile。
- 用 `VLLM_SERVE_GPU_MEMORY_UTILIZATION=0.55/0.70/0.85` 建立 `kv_small/kv_medium/kv_large`。
- saturation 并发先用 32/48/64 smoke。
- daily_dedicated request_rate 0.20/0.35/0.50 smoke。
- sticky_burst request_rate 0.40/0.60/0.80 smoke。
- enterprise request_rate 0.80/1.00/1.20 smoke。
- 选出 12h 完整矩阵使用的 `kv_medium` 主参数，并记录实际 `GPU KV cache size`。

### Phase 2：策略改进

- family_protect 改成 soft_family_budget。
- admission 引入 TinyLFU/ARC 风格的频率-近因融合。
- scheduler 改 bounded two-lane，加入 e2e age guard。
- controller 用 GREEN/YELLOW/RED/LATENCY_RED 调整策略强度。

### Phase 3：短调参与 12h 完整矩阵

- 每次小改后先跑 1-1.5h quick loop。
- 进入完整跑前跑 2-3h mini matrix，确认容量曲线、延迟和低复用保护没有明显问题。
- 12h 完整矩阵包含 capacity_sweep、daily_dedicated_reuse、saturation、sticky_burst、enterprise 和 low_reuse。
- hint_robustness 和 ablation 只作为可选补跑，不进入主 12h。
- 如果 12h v1 不达标，优先修改参数后重跑 quick/mini，不直接再跑完整矩阵。

### Phase 4：选择性复跑

- 如果 12h 完整矩阵已经足够清楚，可以不做更长 formal。
- 若必须增强可信度，只选择最关键模块复跑：daily_dedicated_reuse 2h/policy、saturation_medium 2h/policy、enterprise_normal 1h/policy。
- 选择性复跑控制在 6-10h，不做 60h 级长测。

## 最终建议

下一版项目主线应从“在 27B KV cache 极度紧张下提升吞吐”升级为：

> KVFabric 以 Qwen3.5-9B + 2 x RTX 3090 作为新的主实验设置，把 KV cache 容量显式做成 `kv_small/kv_medium/kv_large` 三档变量。它不会试图在所有负载下强行提升 raw token/s，而是在存在稳定可复用前缀和容量竞争时，减少有价值 KV block 的错误驱逐与 rebuild；在普通和低复用场景中通过自适应 admission 与公平 scheduler 保持低干预；在多轮/长文档场景中用 latency-protected scheduling 争取可观的端到端延迟改善。完整实验矩阵控制在约 12h，短调参 run 控制在 1-3h，以便 3-4 天内多轮试错。

这条叙事更稳，也更符合当前代码和实验结果。

## 2026-06-29 9B 短跑后的架构修正

### 问题复盘

旧 27B saturation 中出现的 35% 以上提升主要来自 SLO 边界放大：KVFabric 降低 rebuilt-from-eviction，让一部分请求从刚好超 SLO 回到 SLO 内，因此 SLO goodput 明显上升。它不是 raw token/s 同比例增长。

换到 Qwen3.5-9B 后，同样的 shared-aware ranking 在中等容量下反而变差。关键原因不是生命周期信号完全无效：旧 9B eviction-only run 中 warm-family hit rate 从 LRU 约 29% 提高到约 44%，说明确实保护到了部分可复用 family；但 25s SLO goodput 从 LRU 约 2051 tok/s 降到约 957 tok/s，说明 selector 的 CPU 开销、free queue 非头部 remove 成本、rank 事件 JSON 构造，以及过强介入共同把延迟推过 SLO 边界。

### 代码修正

1. `block_pool.get_new_blocks` 先检查 LRU 头部 victim 是否真的有高 retain score。没有高价值 victim 时直接走原始 `popleft_n`，不进入 KVFabric selector。
2. 新增 `KVFABRIC_EVICTION_SELECTOR=linear`。线性 selector 按 LRU 顺序扫描，只跳过 retain score 超过阈值的高价值块，并且在候选窗口后方有足够替代块时才跳过；找够低价值 victim 后立即停止。
3. 新增 `KVFABRIC_EVICTION_RANK_MIN_SCORE`，9B 默认 24.0，用于控制介入频率。
4. 9B 默认候选窗口从 512/1024 缩到 64/128，避免把 27B 的大窗口排序成本搬到更快的 9B 服务上。
5. 新增 `KVFABRIC_RANK_LOG_EVENTS=0`，默认短跑不再为每次 eviction ranking 写 `eviction_candidates_ranked` 事件。主生命周期事件仍保留。
6. retain score 的 ranking 路径改用 block meta 中已维护的 family 字段，减少 `family_index` 反查和 refresh。
7. 9B 远程入口补齐 duration/concurrency/window/policy 等环境变量透传，避免短调参命令实际落回 30 分钟默认值。

### 实验修正

`qwen3_5_9b_saturation_reuse_proof_30m.json` 改成更贴近日常长期使用的少用户/小团队场景：

- stable durable/sticky 请求占比提高到约 85%-90%；
- hot family 从 28 降到 12，sticky session 从 160 降到 64；
- cold RAG、transient、burst cold 和 decode-heavy 仍保留，用来制造容量竞争和低复用保护检查；
- KV 容量仍用 0.70 GPU memory utilization 作为 medium，不改成极端占满；
- 主 SLO 改为 20s；SLO probe 保留 18/20/22/25/30/35s，用于避免只挑一个阈值讲故事，并继续检查 25/30/35s 下不劣化。

### 下一步判定标准

短 A/B 先只打开 eviction-only：

- 如果 optimized shared-aware 的 20s SLO goodput 比新 LRU 高 30% 以上，再逐步打开 admission/scheduler；
- 如果 20s 未达标但 25s/30s/35s 接近或更好，说明仍有尾延迟问题，继续收紧 selector 阈值和候选窗口；
- 如果 raw total tok/s 和 SLO goodput 都下降，说明保护收益不够，下一步要进一步降低介入频率或改 retain score；
- 如果 rebuilt-from-eviction 明显下降但 goodput 不升，说明算法方向对、实现开销仍然过高，优先继续优化热路径而不是改场景。

### 9B 迭代结论

9B 上的最终方向不应继续把主证明押在 eviction re-ranking 上。两轮 optimized shared-aware eviction 的 warm-family hit 没有超过 LRU，并且 high_main 延迟变差；这说明在 9B + 中等容量 + 少用户高复用场景下，LRU 的近因优势很强，复杂重排容易保护 stale/deep blocks，破坏自然工作集。

更有效的路径是 `lru_admission`：

- eviction policy 保持原始 LRU；
- admission policy 强制开启；
- durable/high reuse 请求正常 cache；
- cold/bypass/low-reuse/transient discovery tokens 降到 0；
- admission min prompt tokens 降到 400；
- scheduler 关闭，避免调度扫描成本。

代表性 900s 短跑结果：

| metric | LRU | lru_admission | uplift |
|---|---:|---:|---:|
| raw total tok/s | 4530.33 | 4783.73 | +5.59% |
| 18s overall SLO goodput | 1210.09 | 1663.74 | +37.49% |
| 20s overall SLO goodput | 1827.10 | 2231.58 | +22.14% |
| 25s overall SLO goodput | 3432.09 | 4071.63 | +18.64% |
| high_main 20s SLO goodput | 205.41 | 427.82 | +108.28% |
| high_main 22s SLO goodput | 736.41 | 1466.31 | +99.12% |
| high_main 25s SLO goodput | 2647.38 | 3597.19 | +35.88% |
| p50 latency | 21.80s | 20.45s | -6.19% |
| p95 latency | 28.67s | 27.10s | -5.49% |

这比“强行重排 eviction victim”更符合 9B 的成本结构：不在 allocation 热路径排序，不移动 free queue 中的非头部 blocks，只在 cache admission 阶段阻止低复用长上下文污染 KV cache。下一版主实验应将 `lru_admission` 作为 KVFabric 的 9B 主策略，`shared_aware` eviction 只保留为 27B/极高压诊断或后续研究分支。
