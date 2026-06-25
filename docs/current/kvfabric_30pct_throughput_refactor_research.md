# KVFabric 30% 吞吐提升调研与改造方案

日期：2026-06-25

本文档记录从当前约 17%-18% 吞吐提升继续推进到 30% 目标的设计。这里的 30% 指高压闭环
或 fixed-work 实验中的 `goodput_tok_s` 相对 LRU 提升：

```text
uplift = (KVFabric_goodput_tok_s - LRU_goodput_tok_s) / LRU_goodput_tok_s
```

低压场景保留 non-regression 目标。30% 只作为高压、可复用 token 足够多的 workload 目标。

## 已有结果

当前最接近目标的是 2026-06-22 的 10 小时 hint pressure run：

```text
run: experiments/prebenchmark_validation/runs/
     2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long

lru:
  requests: 8040
  throughput: 1522.61 tok/s
  avg latency: 14.943s
  p95 latency: 17.208s
  prefix hit: 5.55%
  rebuilt_from_eviction: 11031

shared_aware:
  requests: 9460
  throughput: 1791.13 tok/s
  uplift: +17.64%
  avg latency: 12.697s
  p95 latency: 16.346s
  prefix hit: 13.43%
  rebuilt_from_eviction: 3486

family_protect:
  requests: 9270
  throughput: 1754.61 tok/s
  uplift: +15.24%
  avg latency: 12.953s
  p95 latency: 16.344s
  prefix hit: 12.14%
  rebuilt_from_eviction: 4711
```

这个结果说明方向有效：prefix hit 上升，rebuilt-from-eviction 下降，闭环固定并发下完成
更多请求。离 30% 还差一段，主要瓶颈已经不在“能不能识别共享 block”，而在调度、admission
和 family 粒度的协同。

## 相关工作给出的启发

- [vLLM/PagedAttention](https://arxiv.org/abs/2309.06180) 的核心收益来自 KV cache 分页、
  减少碎片和支持 request sharing。KVFabric 可以沿着“把 KV block 当作系统资源对象”的
  方向继续做策略层优化。
- [vLLM prefix caching design](https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html)
  采用 block hash 匹配。只要请求 prefix 不对齐或 cached block 已被驱逐，prefill 仍然需要
  重算。
- [SGLang/RadixAttention](https://lmsys.org/blog/2024-01-17-sglang/) 把 prompt 结构抽象成
  radix tree，强调 multi-turn、RAG、agent 和 branching 结构中的 cache-aware execution。
  KVFabric 当前的 family index 只是近似元数据，后续可补成更接近 prefix tree 的运行时结构。
- [Ray/vLLM prefix-aware routing](https://docs.vllm.ai/projects/production-stack/en/vllm-stack-0.1.5/tutorials/prefixaware.html)
  说明在多副本 serving 中保持 prefix locality 可以提升 KV cache 利用率。本项目只有单机单
  vLLM 实例，但同样可以在实例内部做 family/session affinity scheduling。
- [Sarathi-Serve](https://arxiv.org/abs/2403.02310) 用 chunked prefill 和 stall-free batching
  缓解 prefill/decode 干扰。KVFabric 不改 kernel，也可以借鉴其“把大 prefill 切小、让 decode
  不被长 prompt 卡住”的思路。
- [DistServe](https://arxiv.org/abs/2401.09670) 将 goodput 和 TTFT/TPOT SLO 作为核心目标。
  这提醒我们只看 raw tok/s 不够，SLO 内完成的 token 才适合作为主指标。
- [ServeGen](https://arxiv.org/html/2505.09999v3) 和
  [BurstGPT](https://arxiv.org/html/2401.17644v4) 都强调真实 workload 的突发、client skew
  和长度分布差异。30% 目标需要在高压可复用 workload 中成立，同时保留混合流量稳定性实验。

## 当前瓶颈

### 1. Scheduler 只做负向 deferral

现在的 scheduler hook 主要在压力下把低价值 cold miss 转到队尾。它能减少坏情况，但没有
主动选择“马上调度高价值可复用请求”。在闭环高压下，正向选择更重要：一次命中大量 prefix
的请求可以少做 prefill，释放 token budget 和 KV blocks，让后续请求更快进入 batch。

### 2. Eviction 介入偏晚

`BlockPool.get_new_blocks()` 只有在需要新 block 时才从 free-list 候选中选择 victim。此时冷
长 prompt 可能已经占过队列位置，并开始制造 cache pollution。admission 已经缓解了一部分，
但还没有把 request class、family hotness、SLO 和当前 batch 状态放在一起决策。

### 3. family_protect 粒度偏硬

当前 `family_protect` 主要判断 block 是否 protected，然后在线性候选中跳过。它开销低，但
容易出现两类问题：

- 保护过多：深 prefix 或旧热点在后续不再回访时仍占空间；
- 保护不足：新出现但即将高频复用的 session/family 需要几轮之后才被识别。

### 4. prefix hit 比例仍然不够高

10 小时 run 中 shared_aware 的 prefix hit 约 13.43%。这个比例能带来约 17.64% 吞吐提升，
但要稳定达到 30%，需要把高压段有效 hit tokens 推到 18%-25% 以上，或者显著降低冷请求对
KV cache 的污染。

### 5. 计分方式还需要 goodput 化

之前 summary 主要看 total tok/s、avg、p95、rebuilt。下一阶段要按 segment 和 SLO 计算：

```text
goodput_tok_s
successful_tok_s
output_tok_s
TTFT p95/p99
SLO miss rate
completed request mix
```

没有 SLO 的 tok/s 提升不适合作为验收主结论。

## 目标分解

要从 17.64% 推到 30%，至少需要满足其中两项：

```text
prefix hit tokens: 13% -> 20%+
rebuilt_from_eviction: 3486 -> 2500 以下
LRU high-pressure p95: 保持明显高于 KVFabric
KVFabric p95: 不高于 LRU
closed-loop completed requests: 比 LRU 多 25%-35%
```

吞吐提升的路径可以写成：

```text
更好的调度顺序
-> 高价值 family/session 更早命中或更早建立 anchor
-> cold/bypass 请求缓存得更少
-> 共享前缀驻留时间更长
-> prefill 重算减少
-> 同样时间内完成更多请求
```

## 改造路线

### Phase 1：实验和指标先补齐

这部分工作量小，但会直接决定后续优化是否可信。

1. `online_duration_loadgen.py` 和 `online_trace_loadgen.py` 增加 segment 字段：
   `warmup`、`low_guard`、`high_main`、`red_burst`。
2. 每条请求记录：
   `segment`、`request_class`、`tenant_id`、`family_id`、`session_id`、`turn_index`、
   `prompt_tokens`、`output_tokens`、`latency`、`slo_pass`、`error`。
3. summary 脚本增加：
   `goodput_tok_s`、`successful_tok_s`、`output_tok_s`、`completed mix audit`。
4. 新增 fixed-work 校验入口，处理同一批 N 条请求并比较完成时间。

验收输出：

```text
segment_metrics.json
class_segment_metrics.json
completed_mix_audit.json
```

### Phase 2：正向 family/session affinity scheduler

当前 scheduler 以 FCFS 为底，只把低价值请求 defer。下一步增加正向选择窗口：

```text
KVFABRIC_SCHEDULER_AFFINITY=positive
KVFABRIC_SCHEDULER_SCAN_WINDOW=32
KVFABRIC_SCHEDULER_PROMOTE_LIMIT=4
```

在 waiting queue 头部扫描最多 32 个请求，对每个请求计算轻量分数：

```text
score =
  2.5 * estimated_prefix_hit_blocks
  + 1.5 * hot_family_score
  + 1.0 * running_family_affinity
  + 0.8 * durable_hint
  + 0.5 * waiting_age
  - 1.2 * cold_long_miss_penalty
  - 1.0 * bypass_penalty
```

实现上分两级，控制开销：

1. 第一遍只用 hints 和 `HintFamilyRuntime`，不做 prefix lookup；
2. 对 top-K 候选再做已有的 `get_computed_blocks()` 路径，确认实际 hit tokens；
3. 选中请求后按 vLLM 原逻辑分配 tokens 和 slots。

这个策略可以把“可复用请求”提前进入 high_main 的 batch。它比单纯 defer cold miss 更直接，
也是冲 30% 的核心改动。

### Phase 3：session turn-aware admission

新增 hint 字段：

```text
x-kvfabric-session-id
x-kvfabric-turn-index
x-kvfabric-slo-ms
x-kvfabric-hint-confidence
```

admission 根据 session/family 运行状态动态调整缓存预算：

```text
durable hot family:
  GREEN/YELLOW: cache all full blocks
  ORANGE: cache protected prefix + last 1-2 blocks
  RED: cache protected prefix only

sticky session follow-up:
  如果 turn_index > 0 且近期命中过，同 family/session 的 prefix blocks 提高保护深度

cold_rag_unique:
  ORANGE/RED: bypass 或 discovery 0-1 block

transient template:
  前 2 次请求只给 discovery budget
  出现命中或短时间回访后升级为 durable

decode_heavy:
  cache admission 按 prompt hit 情况决定，不因长输出提高保护
```

这样可以减少当前 cold RAG 和 transient ambiguous family 对 prefix cache 的污染。

### Phase 4：soft protected depth 和 per-family cap

把 `family_protect` 从 hard protected 改成 soft budget：

```text
family_score =
  recent_hit_tokens
  + regret_recent
  + branch_count
  + session_followup_count
  - stale_decay

protected_blocks_for_family =
  clamp(base + score_bucket, min=0, max=family_cap)
```

每个 family 的保护深度随时间衰减，避免旧热点长期占空间。环境变量：

```text
KVFABRIC_FAMILY_PROTECT_CAP_BLOCKS=8
KVFABRIC_FAMILY_STALE_DECAY_SECONDS=600
KVFABRIC_FAMILY_REGRET_BOOST_SECONDS=900
KVFABRIC_FAMILY_MIN_HIT_TOKENS=512
```

`is_protected()` 不再只看全局阈值，还要判断 block 是否落在该 family 当前 protection budget
内。这样可以减少 family_protect 过保护，提高有效缓存容量。

### Phase 5：regret feedback 进入 retain score

现在 `EvictedShadow` 已能识别 rebuilt-from-eviction，但反馈还偏统计。下一步把 regret 转成
可衰减的 block/family 权重：

```text
regret_score = rebuilt_count_recent * exp(-age / tau)
retain_score += regret_weight * regret_score
```

并把 regret 写入 `HintFamilyRuntime`，让 scheduler 在高压下优先恢复最近发生过误驱逐的
family。

### Phase 6：chunked prefill 风格的 token budget 协同

不直接改 CUDA/kernel，但可以利用 vLLM 已有的 `long_prefill_token_threshold` 和
`max_num_batched_tokens` 做分段 prefill：

```text
high_main:
  long_prefill_token_threshold: 1024 或 1536
  max_num_batched_tokens: 16384
  max_num_seqs: 16-20
```

目标是避免单个冷长 prompt 占满一个 step 的 token budget。对 KVFabric 来说，这能给
sticky/hot family follow-up 更多进入 batch 的机会。这个方向借鉴 Sarathi-Serve 的 chunked
prefill 思路，但保持在 vLLM scheduler 参数和 Python 控制面内实现。

## 代码改动清单

### vLLM overlay

```text
vllm/v1/core/kvfabric_hints.py
  - 增加 session_id、turn_index、slo_ms、hint_confidence
  - family_key 支持 tenant:session:family 组合模式

vllm/v1/core/kvfabric_lifecycle.py
  - HintFamilyRuntime 增加 recent windows
  - 增加 positive scheduler score
  - 增加 per-family protection budget
  - regret feedback 衰减
  - segment/SLO 字段进入 request events

vllm/v1/core/sched/scheduler.py
  - waiting queue scan window
  - top-K candidate prefix lookup
  - promote reusable request under ORANGE/RED
  - 保留 FCFS fallback 和 env gate

vllm/v1/core/block_pool.py
  - family_protect 使用 soft budget
  - eviction candidate event 增加 family budget 字段
```

### Benchmark

```text
experiments/long_pressure_benchmark/examples/
  online_duration_loadgen.py
  online_trace_loadgen.py
  generate_realistic_trace.py

experiments/long_pressure_benchmark/scripts/
  summarize_remote_27b_benchmark_results.py
  run_remote_27b_saturation_throughput_12h_benchmark.sh
  run_remote_27b_sticky_conversation_trace_12h_benchmark.sh

experiments/long_pressure_benchmark/configs/
  qwen3_5_27b_saturation_throughput_12h.json
  qwen3_5_27b_sticky_conversation_trace_12h.json
```

## 风险和处理

### 扫描 waiting queue 增加调度开销

只在 ORANGE/RED 且非 LRU 策略启用 scan。默认 scan window 32，top-K prefix lookup 4。
summary 增加 scheduler overhead 指标。如果低压回退超过 3%，降低 window 或仅启用 hint-only
score。

### 正向选择破坏公平性

waiting age 加入 score，并设置最大连续 promote 次数。red_burst 可以允许更激进，low_guard
保持 FCFS 或 hint-only。

### hint 错误导致缓存误判

`hint_confidence` 低时只作为弱信号。真实 prefix hit 和 regret feedback 优先级高于 hint。
ambiguous/transient family 采用 discovery budget，不直接按 durable 保护。

### 过度偏向 sticky session

对 one-shot cold noise 单独统计 p95 和 SLO miss。sticky 实验通过标准要求 cold noise latency
不超过 LRU 10%。

### 30% 目标依赖 workload

报告中只在 saturation/sticky 高压实验声明吞吐目标。enterprise mixed trace 主要报告稳定性、
tail latency 和 cache quality。

## 预期路线

优先级按收益和风险排序：

```text
P0: segment/goodput/mix audit
P1: positive family/session scheduler
P2: session turn-aware admission
P3: soft family protection budget
P4: regret feedback decay
P5: chunked-prefill token budget tuning
```

第一轮实现 P0-P2 后即可重新跑 12h saturation。若 best policy 从 17.64% 提到 25% 左右，
继续实现 P3-P4。若 prefix hit tokens 无明显提升，说明 workload 的可复用 token 比例仍不足，
应先加强 sticky/session trace，而不是继续调 retain score。

## 目标验收数字

下一版 12h saturation 的目标：

```text
shared_aware_plus:
  high_main goodput_tok_s >= LRU * 1.25
  rebuilt_from_eviction <= LRU * 0.40
  prefix_hit_tokens >= LRU * 1.50

family_protect_plus:
  high_main goodput_tok_s >= LRU * 1.30
  p95 latency <= LRU * 1.05
  rebuilt_from_eviction <= LRU * 0.35
  low_guard non-regression pass
```

如果最终只有一个策略达到 30%，报告中就以该策略作为主结果，另一个策略作为消融和稳定性
对照。
