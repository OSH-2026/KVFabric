# KVFabric 12h Acceptance Experiment Design

本文档定义 KVFabric 大作业验收用的三组正式长周期实验。目标不是再堆很多零散
benchmark，而是用少量、可复现、可解释的 12h 实验同时证明：

1. 低压下不退化，最好略微改善；
2. 高压下明显提升，尤其是接近或超过 LRU 饱和边界时；
3. KV cache 生命周期管理确实改变了系统行为；
4. 整个系统在 27B、2 x RTX 3090 上能长期稳定运行。

推荐最终验收只保留三组正式实验：

```text
A. saturation_throughput_12h
B. enterprise_mixed_trace_12h
C. sticky_conversation_trace_12h
```

每组实验总时长约 12h，包含三个策略：

```text
lru
shared_aware
family_protect
```

每个策略运行 4h。每个策略内部再拆成短低压段和长高压段：

```text
00:00 - 00:10  warmup, not scored
00:10 - 00:30  low-pressure guard, scored separately
00:30 - 04:00  high-pressure main, primary scored segment
```

这样每个实验都能回答两个问题：

- 低压时 KVFabric 是否不会拖慢正常服务；
- 高压时 KVFabric 是否能显著改善 goodput、延迟、KV rebuild 和 eviction。

高压主段是主要验收依据。低压 guard 只是防止策略为了高压收益牺牲普通使用体验。

## Acceptance Evidence

最终报告必须把证据分成四类。

### 1. Performance Evidence

高压段主要看：

- successful total tokens per second;
- successful requests per second;
- completed requests;
- average latency;
- p95 latency;
- p99 latency, if available;
- timeout/error rate;
- goodput under SLA, if available.

不要只看 raw offered load。高压实验应该强调 successful throughput：

```text
goodput = successful completed output under timeout/SLA
```

如果策略只是接受了更多请求但错误率上升、p95/p99 爆炸，不算成功。

### 2. Cache Lifecycle Evidence

必须同时报告：

- prefix hit rate;
- prefix hit tokens;
- evicted blocks;
- rebuilt_from_eviction_blocks;
- regret proxy;
- touched blocks;
- unique prefix families;
- admission limited events;
- admission saved blocks;
- scheduler defers.

性能提升必须能和 cache 行为对应起来。理想证据链是：

```text
admission/scheduler 改变请求和 cache 压力
-> evicted blocks 下降
-> rebuilt_from_eviction 下降
-> prefix hit tokens 上升或有效保留更稳定
-> latency 下降
-> closed-loop throughput 上升
```

### 3. Stability Evidence

必须报告：

- 12h 是否完整跑完；
- errors 是否为 0；
- vLLM server 是否重启；
- GPU memory 是否稳定；
- 是否 OOM；
- 是否有 request timeout storm；
- 最终进程是否清理干净。

### 4. Workload Realism Evidence

必须记录：

- trace/config SHA256;
- request count;
- request class distribution;
- expected reuse distribution;
- tenant/session/family count;
- prompt token histogram, if available;
- output token histogram, if available;
- pressure mode;
- model, vLLM version, GPU, max_model_len, max_num_seqs, max_num_batched_tokens.

验收报告要能说明 workload 不是为了某个策略临时手调出来的。

## Pressure Design

这三组实验都要尽量高压，但高压不能等于无限堆请求。高压应该定义为：

```text
LRU 接近饱和或明显进入 cache-pressure/red-zone；
KVFabric 仍能稳定完成更多有效工作或显著减少 cache damage。
```

建议使用四个压力层级，但正式 12h 实验只保留两个 scoring segment：

| Level | 用途 | 说明 |
|---|---|---|
| GREEN | low-pressure guard | GPU 有余量，请求不排队，证明不退化 |
| YELLOW | calibration only | 找到 LRU 开始排队的边界 |
| ORANGE | high-pressure main | 推荐主压力，LRU 有明显 cache churn，但不崩 |
| RED | overload boundary | 可短时间插入，证明极限下 goodput/尾延迟优势 |

每个 12h 正式实验中：

- low-pressure guard 用 GREEN；
- high-pressure main 用 ORANGE 为主；
- 可以在 high-pressure main 内加入少量 RED burst；
- 不建议整段都跑无界 RED，因为那会变成排队崩溃测试。

推荐主判断：

```text
高压不是让所有策略都 timeout。
高压是让 LRU 明显吃亏，但系统仍有足够成功请求可以比较。
```

## Common Run Layout

每个实验总计 12h：

| Policy | Wall time | Warmup | Low guard | High main |
|---|---:|---:|---:|---:|
| lru | 4h | 10m | 20m | 210m |
| shared_aware | 4h | 10m | 20m | 210m |
| family_protect | 4h | 10m | 20m | 210m |

每个策略使用同一份 trace 或同一份 deterministic scenario seed。不同策略不能重新随机生成不同 workload。

每个策略输出至少包含：

```text
online_trace/metrics.json
online_trace/class_metrics.json
online_trace/rolling_metrics.jsonl
online_trace/prometheus_cache_samples.jsonl
online_trace/raw_outputs_sample.jsonl
kvfabric_lifecycle_metrics.json
prometheus_metrics_summary.json
prometheus_metrics_summary.txt
```

raw `kvfabric_lifecycle.jsonl` 可以保留远程，不默认提交 Git。

## Experiment A: saturation_throughput_12h

### Purpose

这是最重要的性能收益实验。它要复现并正式化之前 hint pressure 10h 中接近
20% 的吞吐提升。

之前的结果来自 closed-loop / fixed-concurrency pressure：

```text
lru:          1522.61 tok/s, 8040 requests
shared_aware: 1791.13 tok/s, 9460 requests, +17.64%
family:       1754.61 tok/s, 9270 requests, +15.24%
```

这类实验的特点是：固定并发和固定时长，谁的平均延迟更低、cache rebuild 更少，谁就能完成更多请求。

### Workload

基于原 `qwen3_5_27b_hint_pressure_10h`，但整理成正式 12h suite：

```text
qwen3_5_27b_saturation_throughput_12h
```

请求类型建议：

| Class | 占比 | 目的 |
|---|---:|---|
| hot_family | 30-35% | 长期稳定前缀，证明 reuse 收益 |
| cold_rag | 35-45% | 制造 cache churn，压迫 eviction |
| transient_family | 15-20% | 短期共享，测试 admission 判断 |
| cold_rag_burst | 3-8% | 周期性 RED burst |
| decode_heavy | 3-5% | 防止只优化 prefill |

这个 workload 应该比 enterprise mixed 更“压榨”系统，因为它的主要目的就是性能证明。

### Pressure Mode

使用 closed-loop fixed-concurrency。

建议配置：

```text
max_model_len: 4096
max_num_seqs: 10 or 12
max_num_batched_tokens: 8192, then 16384 if stable
concurrency low guard: 3-4
concurrency high main: 10-14
RED burst concurrency: high + 20-30%
generation max_tokens: 32 or 64
```

具体高压值要先用 LRU 做 10-20 分钟 calibration：

```text
concurrency = 8, 10, 12, 14
```

选择规则：

- LRU p95 明显上升；
- LRU rebuilt/evicted 明显增加；
- LRU error rate 仍为 0 或小于 0.5%；
- KVFabric 有空间展示优势。

如果 LRU 已经 timeout storm，压力太高；如果三策略都完全无排队，压力太低。

### Primary Metrics

高压主段：

- total tok/s;
- req/s;
- completed requests;
- avg latency;
- p95 latency;
- rebuilt_from_eviction;
- evicted blocks;
- prefix hit tokens.

低压 guard：

- avg/p95 latency 不高于 LRU 超过 3%;
- tok/s 不低于 LRU 超过 3%;
- errors = 0。

### Success Criteria

强成功：

```text
best KVFabric policy total tok/s >= LRU +15%
p95 latency <= LRU
rebuilt_from_eviction <= LRU -50%
errors = 0
```

可接受成功：

```text
best KVFabric policy total tok/s >= LRU +10%
p95 latency <= LRU +5%
rebuilt_from_eviction <= LRU -40%
errors = 0
```

失败但机制有效：

```text
tok/s 没提升，但 rebuilt/evicted 明显下降。
这种只能证明生命周期机制有效，不能证明性能收益。
```

## Experiment B: enterprise_mixed_trace_12h

### Purpose

这是“真实企业混合负载”的稳定性和机制实验。它不应该作为吞吐提升主证据，因为 open-loop fixed-arrival trace 下，如果所有策略都能吃完同样的 offered load，tok/s 自然接近。

它证明的是：

- 12h 真实混合负载稳定；
- 策略不会导致错误、OOM 或崩溃；
- eviction/rebuild/admission 行为确实改善；
- 在真实分布下低压不退化，高压不崩。

### Workload

保留当前 `enterprise_mixed` profile，但将压力段设计得更明确：

| Class | 目的 |
|---|---|
| agent_tool_loop | 多轮工具链和 durable context |
| multi_turn_support | 会话式共享上下文 |
| rag_qa_hot_docs | 热文档前缀复用 |
| rag_qa_cold_docs | 冷 RAG churn |
| tenant_workflow_hot | 租户级工作流共享 |
| decode_heavy_report | decode-heavy 防偏 |
| extraction_classification | 短请求和 unknown hints |

当前 12h trace 已经完成一次，结果显示三策略 tok/s 接近，但 cache 行为差异明显：

```text
lru rebuilt: 1846
shared_aware rebuilt: 1235, -33.10%
family_protect rebuilt: 768, -58.40%
```

这说明 enterprise trace 可以作为机制和稳定性证据。

### Pressure Mode

使用 open-loop deterministic trace，但不要只跑平稳低压。建议 trace 内置阶段：

```text
0-10m warmup
10-30m GREEN low guard
30-90m ORANGE pressure
90-120m RED burst
120-240m ORANGE pressure
```

每个策略 4h 重放同一份 trace。

推荐参数：

```text
target request rate low guard: 0.06-0.10 req/s
target request rate high main: 0.20-0.30 req/s
RED burst local rate: high + 30-50%
max_in_flight: 32 or 48
max_model_len: 4096
max_num_seqs: 10
max_num_batched_tokens: 8192
```

当前已经跑过的 `0.18 target / 0.196 actual` 比较稳，但不够展示吞吐差异。下一版 enterprise trace 可以提高到 `0.24-0.28`，或者在中间插入 RED burst。

### Primary Metrics

不要把 tok/s 提升作为主判断。主指标是：

- errors;
- p95/p99 latency 是否可控；
- rebuilt_from_eviction;
- evicted blocks;
- admission saved blocks;
- scheduler defers;
- per-class latency;
- per-class errors.

### Success Criteria

强成功：

```text
12h complete
errors = 0
rebuilt_from_eviction <= LRU -50%
evicted blocks <= LRU -40%
p95 latency <= LRU +5%
```

可接受成功：

```text
12h complete
errors = 0
rebuilt_from_eviction <= LRU -30%
evicted blocks <= LRU -30%
p95 latency <= LRU +10%
```

如果 tok/s 没变化，不算失败；这是 open-loop trace 的预期。

## Experiment C: sticky_conversation_trace_12h

### Purpose

这是长上下文多轮对话场景。它专门回答：

```text
当多轮会话天然具有高 prefix reuse 时，KVFabric 是否能保住并利用这些 prefix？
```

这个实验应该比 enterprise mixed 更有机会显示 prefix reuse 和性能收益。

### Workload

必须使用冻结 trace，不要实时让模型自己和自己对话。

原因：

- 实时自对话不可复现；
- 不同策略会改变响应内容，从而改变后续 prompt；
- A/B 不再公平。

推荐流程：

1. 离线生成或手写多轮 transcripts；
2. 冻结为 deterministic prompt sequence；
3. 三个策略重放完全相同的 trace；
4. 记录 trace SHA256。

会话设计：

| Component | 说明 |
|---|---|
| system prompt | 长且稳定，所有 session 共享一部分 |
| tenant context | 租户级稳定前缀 |
| session memory | 每个会话不断增长 |
| tool policy | 多轮固定工具规则 |
| user turn tail | 每轮少量变化 |
| retrieved snippets | 部分热文档反复出现，部分冷文档只出现一次 |

推荐分布：

| Class | 占比 | 说明 |
|---|---:|---|
| sticky_support_session | 45-55% | 8-20 轮客服/助手对话 |
| sticky_agent_session | 20-30% | 多轮工具调用规划 |
| sticky_rag_session | 15-20% | 热文档反复引用 |
| one_shot_cold | 5-10% | 防止策略只服务高复用请求 |

### Pressure Mode

建议使用 open-loop trace + high in-flight cap，或者 closed-loop session scheduler。为了验收更直接，推荐两段式：

```text
low guard: open-loop low rate, prove no regression
high main: open-loop high rate with max_in_flight cap, plus burst
```

参数建议：

```text
max_model_len: 4096, optionally 6144 if memory permits
max_num_seqs: 8-10
max_num_batched_tokens: 8192 or 12288
target request rate low guard: 0.05-0.08 req/s
target request rate high main: 0.18-0.25 req/s
max_in_flight: 32
session count: 200-500
turns per session: 8-20
```

如果目标是更强性能证明，可以使用 closed-loop sticky variant：

```text
concurrency: 8-12 sessions
每个 session 依次推进 turns
```

但正式验收建议仍保持 deterministic trace replay，避免公平性争议。

### Primary Metrics

这个实验最重要的是：

- prefix hit rate;
- prefix hit tokens;
- TTFT/prompt latency, if available;
- rebuilt_from_eviction;
- per-session completion;
- total tok/s under high pressure;
- p95 latency.

### Success Criteria

强成功：

```text
prefix hit tokens >= LRU +30%
rebuilt_from_eviction <= LRU -50%
high-pressure total tok/s >= LRU +10%
p95 latency <= LRU
errors = 0
```

可接受成功：

```text
prefix hit/rebuilt 明显优于 LRU
p95 latency <= LRU +5%
tok/s 不低于 LRU
errors = 0
```

如果 sticky conversation 也没有 prefix hit 提升，要重点检查：

- trace 是否真的复用了 token-identical prefix；
- chat template 是否导致前缀不一致；
- request ordering 是否破坏了 cache locality；
- max_model_len / max_num_seqs 是否导致可保留 cache 太小；
- family hint 是否准确传入。

## Low-Pressure Proof

低压证明不需要单独跑 12h。每个 12h 实验内部保留 20 分钟 GREEN guard 即可。

低压 guard 的目的不是证明收益，而是证明：

```text
KVFabric 不会在普通服务压力下明显拖慢系统。
```

报告中单独列：

| Metric | Acceptance |
|---|---|
| avg latency | <= LRU +3% |
| p95 latency | <= LRU +5% |
| tok/s / req/s | >= LRU -3% |
| errors | 0 |
| GPU memory | no abnormal growth |

如果低压略微提升，可以作为加分项；但不要把低压作为主要贡献。

## High-Pressure Proof

高压主段要占每个策略 4h 中的大部分时间。建议至少 210 分钟。

高压主段验收优先级：

1. goodput/tok/s 提升；
2. p95/p99 不恶化或改善；
3. rebuilt/eviction 大幅下降；
4. errors = 0；
5. per-class 没有严重牺牲某类请求。

高压配置选择不要只追求“数字好看”，要避免不可解释：

- 如果 LRU 已经大量 timeout，KVFabric 赢了也说服力弱；
- 如果所有策略都完全 idle，KVFabric 没机会展示收益；
- 最好让 LRU 处于“能跑完但明显吃力”的状态。

推荐报告同时展示：

```text
GREEN guard: not worse
ORANGE main: clear improvement
RED burst: graceful degradation
```

## Reporting Template

最终验收报告建议按以下结构：

```text
1. Environment
   - model, vLLM version, GPU, venv, commit SHA

2. Workload
   - suite name, trace hash, request count, class distribution

3. Low-pressure guard
   - latency/tok/s/errors vs LRU

4. High-pressure main
   - tok/s, req/s, completed, latency, errors

5. KV lifecycle
   - prefix hit, evicted, rebuilt, regret, admission, scheduler

6. Per-class fairness
   - no class starves or regresses catastrophically

7. Verdict
   - strong success / acceptable success / mechanism-only / failed
```

关键表格：

| Policy | Segment | Req/s | Tok/s | vs LRU | Avg | P95 | Errors |
|---|---|---:|---:|---:|---:|---:|---:|

| Policy | Segment | Prefix hit | Evicted | Rebuilt | Rebuilt vs LRU | Saved blocks |
|---|---|---:|---:|---:|---:|---:|

| Class | Policy | Completed | Tok/s | Avg | P95 | Errors |
|---|---|---:|---:|---:|---:|---:|

## Recommended Final Acceptance Set

### Required

```text
1. saturation_throughput_12h
2. enterprise_mixed_trace_12h
3. sticky_conversation_trace_12h
```

### Optional Short Ablations

如果时间允许，用 30-60 分钟短跑补充：

```text
shared_aware only
family_protect only
admission off
scheduler defer off
hints off
```

这些不需要 12h。它们是因果解释，不是主验收。

## Expected Best Narrative

如果实验结果理想，最终叙事应该是：

```text
KVFabric 在低压下不明显退化。
在高压 fixed-concurrency 下，shared-aware / family-protect 通过降低 eviction
和 rebuilt-from-eviction，把延迟下降转化为更多 completed requests，从而提升
successful tok/s。
在真实 enterprise mixed trace 下，open-loop 吞吐不必提升，但系统 12h 稳定，
cache damage 明显降低。
在 sticky conversation 长上下文场景下，KVFabric 能更好保住 session/document
prefix，在高复用场景中展示更强 prefix hit 和更低 rebuilt。
```

如果只有 saturation 提升，而 enterprise trace tok/s 不变，也可以接受：

```text
两类实验测量对象不同。
saturation 证明容量上限；
enterprise trace 证明真实负载稳定性和生命周期质量。
```

## Immediate Next Implementation Steps

1. 新增 `qwen3_5_27b_saturation_throughput_12h.json`。
2. 新增 `qwen3_5_27b_sticky_conversation_trace_12h.json`。
3. 扩展 trace generator 支持 per-policy segment labels：
   `warmup`, `low_guard`, `high_main`, `red_burst`。
4. 扩展 summary 脚本，按 segment 分别输出低压和高压指标。
5. 对已有 `enterprise_mixed_trace_12h` 加 segment-aware summary。
6. 正式重跑三组 12h，保留 trace hash、metrics、summary、job log。
