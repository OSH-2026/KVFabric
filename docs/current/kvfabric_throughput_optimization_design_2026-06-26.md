# KVFabric 吞吐优化复盘与下一轮实现方案

日期：2026-06-26

本文档记录 12 小时 `saturation_throughput` 长测后的复盘，以及下一轮代码改造和 4 小时回归实验方案。目标仍然是把高压段 goodput 提升推到 30% 左右，同时保留低压 non-regression 证据。

## 结果输入

本轮复盘以这次 12 小时 saturation run 为主：

```text
run:
  experiments/long_pressure_benchmark/runs/
  2026-06-25_144724_qwen3_5_27b_qwen3_5_27b_saturation_throughput_12h_long

model:
  Qwen/Qwen3.5-27B-FP8

hardware:
  robowalker, 2 x RTX 3090 24GB

policies:
  lru, shared_aware, family_protect
```

关键结果：

| Segment | Policy | Completed | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency |
| :-- | :-- | --: | --: | --: | --: | --: |
| low_guard | lru | 575 | 1222.53 | +0.00% | 1243.96 | 10.254s |
| low_guard | shared_aware | 582 | 1234.21 | +0.96% | 1255.65 | 10.551s |
| low_guard | family_protect | 573 | 1211.51 | -0.90% | 1239.02 | 10.308s |
| high_main | lru | 6358 | 556.18 | +0.00% | 1444.50 | 31.569s |
| high_main | shared_aware | 6472 | 643.53 | +15.71% | 1470.70 | 30.734s |
| high_main | family_protect | 6333 | 521.34 | -6.26% | 1439.22 | 31.526s |
| red_burst | lru | 675 | 39.19 | +0.00% | 1456.22 | 37.138s |
| red_burst | shared_aware | 686 | 76.45 | +95.05% | 1479.95 | 37.762s |
| red_burst | family_protect | 668 | 27.45 | -29.95% | 1435.79 | 37.136s |

KV cache 侧证据：

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 357,504 | 1.79% | 12,680 | +0.00% | 0 | 0 |
| shared_aware | 702,464 | 2.94% | 3,566 | -71.88% | 14,501 | 1,746 |
| family_protect | 224,224 | 0.96% | 3,966 | -68.72% | 14,758 | 1,651 |

结论：

1. 低压段没有退化。`shared_aware` 略快，`family_protect` 略慢但仍在可接受范围。
2. 高压主段 `shared_aware` 的 goodput 提升是 +15.71%，低于 30% 目标。
3. `shared_aware` 大幅减少 rebuilt-from-eviction，但 prefix hit rate 只到 2.94%。这说明策略已经减少了坏驱逐，仍没有把足够多的高价值请求提前送入 batch。
4. `family_protect` 减少 rebuilt 的效果接近 `shared_aware`，但 prefix hit tokens 反而更低，说明它保护了不少价值不高或时效已过的 block。
5. red_burst 里 `shared_aware` 的 SLO goodput 提升很大，说明策略在过载边界能保住一部分高价值请求。raw total tok/s 提升只有 1%-2%，瓶颈已经从“GPU 是否满载”转成“同样 GPU token budget 下哪些 token 算有效工作”。

## 相关工作

本项目只引用和下一步设计直接相关的结论。

- [PagedAttention/vLLM](https://arxiv.org/abs/2309.06180) 把 KV cache 分页化，减少碎片，并支持 request sharing。KVFabric 的策略层优化仍然建立在 block hash 和 block pool 这套机制上。
- [vLLM prefix caching design](https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html) 说明 prefix cache 的命中来自完整 block hash 匹配。调度侧提前选择命中更多 block 的请求，可以减少 prefill token。
- [SGLang/RadixAttention](https://lmsys.org/blog/2024-01-17-sglang/) 把 multi-turn chat、RAG、agent、few-shot 等场景抽象成前缀树复用问题。KVFabric 当前还没有完整 radix tree，但可以先用 family/session hint 近似 locality。
- [Sarathi-Serve](https://arxiv.org/abs/2403.02310) 通过 chunked prefill 和 batching 策略降低 prefill/decode 干扰。KVFabric 暂不改 kernel，可以先在 scheduler 层减少低复用长 prefill 对 batch 的占用。
- [DistServe](https://arxiv.org/abs/2401.09670) 强调 goodput 和 latency SLO。验收时应把 SLO 内 token 作为主指标，raw tok/s 只能解释 GPU 是否被打满。
- [Orca](https://www.usenix.org/conference/osdi22/presentation/yu) 的 iteration-level scheduling 说明 LLM serving 需要细粒度调度。KVFabric 下一步不只做 eviction，还要影响 waiting queue 进入运行队列的顺序。
- [BurstGPT](https://arxiv.org/abs/2401.17644) 和 [ServeGen](https://arxiv.org/abs/2505.09999) 都强调真实流量里的突发、client skew、长度分布漂移和多类请求混合。12 小时验收方案里的 low/high/red 分段和三类 trace 继续保留。

## 子 agent 分析汇总

三路分析基本一致：

1. 当前收益主要来自减少坏驱逐。这个收益真实，但不足以稳定达到 30%。
2. 正向 scheduler 是下一轮最重要的方向。现在只有 hint-based positive promotion，没有核对实际 prefix hit。
3. `family_protect` 的保护太硬，容易保护旧热点。它需要软预算、时效衰减和真实 hit feedback。
4. 长压结果需要按 segment、request class、SLO pass/miss 拆开。已经新增 `class_segment_metrics.json`，后续 4 小时 run 会带上。
5. 如果要证明高压收益，需要把主结论放在 `high_main.goodput_total_tokens_per_second`，同时展示 cache 证据链。

## 30% 目标拆解

30% 的 high_main goodput uplift 可以来自三部分叠加：

```text
1. prefix hit token 增加
   fewer prefill tokens -> same GPU time finishes more useful requests

2. cold long miss 减少污染
   fewer low-value cached blocks -> hot family survives longer

3. batch admission 更偏向高价值请求
   same queue pressure -> more SLO-pass work
```

这次 high_main 的 `shared_aware` 已经做到：

```text
rebuilt_from_eviction: -71.88%
prefix_hit_tokens: +96.49%
goodput: +15.71%
```

差距在于 prefix hit 绝对比例仍低。下一轮先把 scheduler 从“只看 hint 的正向选择”改成“hint 预选 + 实际 prefix hit 校验”。这个改动有三个好处：

1. 开销可控，只对 waiting queue 头部少量 top-K 做真实 cache lookup。
2. 命中多的请求会更早进入 batch，直接减少本步 prefill。
3. `request_promoted` 日志能记录 `estimated_hit_tokens`，便于确认提升是否来自真实复用。

## 本轮代码改造

### P0：指标已补齐

已完成：

```text
class_segment_metrics.json
segment active phase header
SLO pass/miss
error kind
per-request token means
acceptance_analysis.md
```

这保证 4 小时实验可以判断每个 request class 在 low/high/red 里的表现，避免闭环吞吐差异掩盖 workload drift。

### P1：hit-aware positive scheduler

当前 scheduler 的 positive promotion 流程：

```text
scan waiting queue head window
-> tracker.positive_request_score()
-> promote best request if score margin passes
```

问题是 `positive_request_score()` 主要来自 hint、family runtime 和 prompt length 惩罚。hint 有用，但不能保证这个请求当前真的能命中 prefix cache。下一版改为两级打分：

```text
stage 1:
  对 scan window 内请求做 hint score。

stage 2:
  从 hint score 最高的 top-K 请求中调用 peek_computed_tokens()。
  这个函数只查询当前 prefix cache 命中 token，不写 prefix stats，也不发 lifecycle event。

final score:
  hint_score
  + estimated_hit_tokens * KVFABRIC_SCHEDULER_POSITIVE_HIT_WEIGHT
  + durable session bonus
```

新增环境变量：

```text
KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE=1
KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK=4
KVFABRIC_SCHEDULER_POSITIVE_HIT_WEIGHT=0.004
```

事件增强：

```text
request_promoted:
  estimated_hit_tokens
  hit_aware
  hit_topk
  selected_base_score
  selected_hit_bonus
```

预期效果：

```text
shared_aware:
  high_main prefix hit tokens 增加
  rebuilt_from_eviction 不上升
  scheduler promotes 里 estimated_hit_tokens 均值上升
  high_main goodput 从 +15.71% 往 +20%-25% 推进
```

### P2：session turn-aware scoring

sticky conversation 里，同一个 session 的后续 turn 理论上应该有较高 prefix cache 复用。现在 hint 中已经有 `session_id` 和 `turn_index`，但 scheduler 打分使用得比较保守。下一版加入轻量规则：

```text
turn_index > 0 且 expected_reuse=durable:
  +1.5

同 family 最近有 prefix hit:
  +min(hit_ratio * 4.0, 2.0)

同 family 最近被 admission limit，但仍有 hit:
  不再直接降低分数；只降低低命中 family。
```

这部分主要服务 `sticky_conversation_trace_4h`，也会影响 saturation workload 中 durable hot family。

### P3：低复用长请求的 admission 更硬

`low_reuse` 和 `bypass` 在高压下不应把大量完整前缀写进 cache。当前 discovery token 默认已经调得很低，但 transient/cold 仍可能带来污染。下一轮暂不大改 block allocation，只把策略默认值收紧：

```text
KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS=512
KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS=3072
KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS=512
```

这样能把预算让给有真实命中的 durable family，同时避免 durable 新 family 完全无法建立 anchor。

### P4：family_protect 暂不作为主优化对象

12 小时结果显示 `family_protect` 这条线当前收益不稳定。它减少 rebuilt，但没有转成 prefix hit。短期内不把它作为冲 30% 的主路径，只保留在实验中作为对照。

后续单独改 `family_protect` 时再做三件事：

```text
soft quota per family
stale family decay
protect only high-regret/high-hit blocks
```

## 4 小时验证计划

代码改完后先跑：

```text
experiments/long_pressure_benchmark/configs/
qwen3_5_27b_saturation_throughput_4h.json
```

原因：

1. saturation 是当前最直接的吞吐目标。
2. 4 小时版本和 12 小时版本只改持续时间，适合快速比较趋势。
3. 新增 `class_segment_metrics.json` 后，可以确认提升是否来自某一类请求的偶然偏移。

验收看这些字段：

```text
high_main.goodput_total_tokens_per_second
high_main.slo_miss_rate
high_main.class_segment_metrics
red_burst.goodput_total_tokens_per_second
kvfabric_lifecycle_metrics.prefix_hit_tokens
kvfabric_lifecycle_metrics.rebuilt_from_eviction
request_promoted.estimated_hit_tokens
```

如果 4 小时 saturation 有明显改善，再跑：

```text
enterprise_mixed_trace_4h
sticky_conversation_trace_4h
```

## 风险与处理

### 风险 1：peek cache hit 增加 scheduler 开销

控制方法：

```text
top-K 默认 4
只在 pressure >= positive_min_risk_ratio 时启用
只在 scan window 内先 hint 预选
```

如果 CPU 开销明显上升，把 top-K 降到 2，或只在 `waiting_queue_size >= 8` 时启用。

### 风险 2：promotion 破坏 FCFS 公平性

控制方法：

```text
positive_score_margin 默认 4.0
positive_max_per_step 默认 4
queue_index 仍有惩罚
request_promoted 记录原 queue_index
```

报告中展示 class drift 和 max class drift。如果 drift 超过 3 percentage points，结论要降级。

### 风险 3：durable family 过度倾斜

控制方法：

```text
durable session bonus 不超过 1.5
hit bonus 来自真实 cache hit
red_burst 单独检查 timeout/error
```

如果 `durable_hot_family` 占比过高但总 goodput 提升不明显，说明 scheduler 只是在换请求类型，需要回退加权。

### 风险 4：family_protect 继续拖低结果

本轮结论主推 `shared_aware`。`family_protect` 继续跑，但只作为策略边界和失败样本分析。后续要把它改成 soft protection 后再重新进入主线。

## 预期提交顺序

```text
1. 记录 12h saturation 结果
2. 写入本设计文档
3. 实现 hit-aware positive scheduler
4. 部署远程 overlay
5. 启动 saturation_throughput_4h
6. 4h 完成后同步结果并提交
```

如果 GitHub 网络临时不可用，本地仍按这个顺序提交。网络恢复后一次性 push，提交历史保持清楚。
