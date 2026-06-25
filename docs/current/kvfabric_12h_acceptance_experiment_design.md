# KVFabric 12h 长测验收方案

日期：2026-06-25

本文档定义 KVFabric 期末验收使用的 12 小时长周期实验。实验目标是用少量固定
workload 证明两件事：低压力正常使用场景下不出现性能回退，高压力场景下通过更好的
KV cache 生命周期管理获得可观收益。正式报告只保留三组实验，避免大量短测结果互相
干扰。

```text
A. saturation_throughput_12h
B. enterprise_mixed_trace_12h
C. sticky_conversation_trace_12h
```

三组实验都在同一台远程机器上运行：

```text
host: robowalker
GPU: 2 x RTX 3090 24GB
vLLM: 0.22.1 + KVFabric overlay
model: Qwen/Qwen3.5-27B-FP8
profile: qwen3_5_27b
policies: lru, shared_aware, family_protect
```

## 外部依据

真实 LLM serving 负载没有统一比例。公开资料更适合提供建模边界：

- [BurstGPT](https://arxiv.org/html/2401.17644v4) 给出了 Azure OpenAI 区域服务的
  长周期 trace，重点特征包括突发、服务类型差异、conversation/API 入口差异和失败率。
- [ServeGen](https://arxiv.org/html/2505.09999v3) 从生产 trace 总结出 client skew、
  突发性和长度分布漂移，并给出输入长度混合 Pareto/lognormal、输出长度 exponential
  的建模方向。
- [IETF LLM serving workload profiles](https://datatracker.ietf.org/doc/html/draft-mondal-llm-serving-workload-profiles-00)
  将 LLM serving 按 minimal-output、interactive streaming、prefill-heavy、
  decode-heavy、multi-step chained 等类别拆分。
- [vLLM/PagedAttention](https://arxiv.org/abs/2309.06180) 说明 KV cache 的分页管理和
  request sharing 直接影响并发容量和吞吐。
- [vLLM prefix caching design](https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html)
  说明 prefix caching 依赖 block hash 匹配，收益主要来自共享前缀的 prefill 复用。
- [SGLang/RadixAttention](https://lmsys.org/blog/2024-01-17-sglang/) 将 multi-turn chat、
  RAG、agent、few-shot、self-consistency 等模式归为常见共享 prompt 结构。
- [Sarathi-Serve](https://arxiv.org/abs/2403.02310) 和
  [DistServe](https://arxiv.org/abs/2401.09670) 都把 prefill/decode 干扰、chunked
  prefill、goodput 和 SLO 作为 LLM serving 评测重点。

本项目的验收 workload 由这些约束合成，报告中记录 seed、trace hash、请求类型比例、
长度分布和 hint 分布，避免事后根据某个策略手调数据。

## 通用执行结构

每组实验总时长 12 小时，三种策略各 4 小时。每个策略内部使用相同分段：

```text
00:00 - 00:10  warmup，不计入验收
00:10 - 00:30  low_guard，低压不退化检查
00:30 - 03:40  high_main，高压主计分段
03:40 - 04:00  red_burst，过载边界段
```

高压段占 190 分钟，red burst 占 20 分钟。低压段只用于 non-regression。正式结论以
high_main 和 red_burst 为主，low_guard 作为保底证据。

每个实验输出四类汇总：

```text
segment_metrics.json
class_metrics.json
kvfabric_lifecycle_metrics.json
remote_27b_benchmark_summary.md
```

summary 按 `warmup`、`low_guard`、`high_main`、`red_burst` 分段展示结果。

## 压力校准

正式 12h 长测之前先跑 20-30 分钟校准。校准只用于确定压力参数，不进入验收结果。

### 校准步骤

1. 使用 LRU 运行同一 workload 的 5 分钟 low profile，记录低压 avg/p95、GPU 利用率、
   waiting queue、prefix hit 和 timeout。
2. 逐级增加并发或到达率，直到 LRU 进入 ORANGE 区间。
3. 在 ORANGE 参数上额外加 25%-40% burst，作为 red_burst。
4. 三种策略使用同一组最终参数，不为 KVFabric 单独调低或调高压力。

### 压力分区

```text
GREEN:
  waiting queue 基本为 0
  p95 latency 接近 low profile
  无 timeout

YELLOW:
  waiting queue 偶尔堆积
  p95 latency 约为 low profile 的 1.2x-1.5x
  cache pressure 开始出现

ORANGE:
  LRU 的 p95 latency 约为 low profile 的 1.5x-2.5x
  waiting queue 持续存在
  rebuilt_from_eviction 明显上升
  GPU 利用率接近饱和，或 KV cache free head window 持续紧张

RED:
  到达率或闭环并发在 ORANGE 基础上增加 25%-40%
  允许 LRU 出现明显 tail latency 和少量 SLO miss
  不接受 OOM、server crash、持续 timeout storm
```

高压参数以 ORANGE 为主。RED 只占最后 20 分钟，用于观察策略在边界条件下的稳定性。

### 远程初值

2 x RTX 3090 24GB + Qwen3.5-27B-FP8 可先从下列参数校准：

```text
max_model_len: 4096
max_num_seqs: 16
max_num_batched_tokens: 16384
closed-loop high concurrency: 16
closed-loop red concurrency: 20-22
open-loop high max_in_flight: 48
open-loop red max_in_flight: 64
open-loop high target_rps: 0.26-0.34
open-loop red target_rps: high target 的 1.25x-1.40x
```

如果 LRU 在 5 分钟内发生 OOM 或超过 10% timeout，降低一个档位。如果 LRU 的
waiting queue 长时间为 0，继续升压。

## 计分指标

### 低压 non-regression

low_guard 只做不退化检查。KVFabric 策略满足下列条件即可：

```text
avg latency <= LRU * 1.03
p95 latency <= LRU * 1.05
successful tok/s >= LRU * 0.97
successful req/s >= LRU * 0.97
errors == 0
server restart == 0
```

低压略微提升可以记录，但不作为主要贡献。

### 高压主指标

high_main 主指标采用 goodput，而不是 raw offered load：

```text
goodput_tok_s = SLO 内成功完成的 token 数 / 计分秒数
successful_tok_s = 成功完成的 token 数 / 计分秒数
successful_req_s = 成功完成的请求数 / 计分秒数
```

闭环实验优先看 `goodput_tok_s` 和 `successful_tok_s`。开环 trace 优先看
`goodput_tok_s`、p95/p99、SLO miss、queue backlog 和 timeout。

验收采用相对 LRU 的 uplift：

```text
uplift = (KVFabric_high_main_goodput_tok_s - LRU_high_main_goodput_tok_s)
         / LRU_high_main_goodput_tok_s
```

### KV cache 证据

每组实验同时报告：

```text
prefix hit tokens
prefix hit rate
evicted blocks
rebuilt_from_eviction blocks
admission limited events
admission saved blocks
scheduler defers
hint coverage
top families by hit tokens
top families by regret
```

性能提升要能和 cache 行为对应起来。最理想的证据链是：

```text
高压下 admission/scheduler 改变缓存压力
-> 低价值 cold blocks 更少进入 prefix cache
-> 共享前缀被驱逐得更少
-> rebuilt_from_eviction 下降
-> prefill work 下降
-> closed-loop goodput 上升，open-loop tail latency 下降
```

## 公平性控制

### 固定 seed 与请求池

三种策略使用同一个 config、seed 和 payload pool。正式报告记录：

```text
config SHA256
trace SHA256
payload count
request class distribution
prompt token histogram
output token histogram
hint distribution
```

### 闭环实验的请求池偏差

闭环 fixed-concurrency 会出现一个天然问题：更快的策略在同样时间内跑到请求池后面更多
位置。如果请求池前后分布不同，吞吐差异会混入 workload 差异。正式实验采用两层控制：

1. payload pool 用固定 seed 生成并全局 shuffle，保证长时间区间内类别分布稳定；
2. summary 统计每种策略实际完成请求的 class/session/family 占比。

验收阈值：

```text
completed class mix difference <= 3 percentage points
completed prompt-token mean difference <= 5%
completed output-token mean difference <= 5%
```

超出阈值时保留结果，但在报告中标注为 workload drift，并补跑 fixed-work 子实验。

### Fixed-work 子实验

每个 12h 实验可以附带一个 30-60 分钟 fixed-work 子实验。三种策略处理完全相同的
N 条请求，比较完成时间、goodput 和 p95。它不替代 12h 长测，只用于校验闭环结果没有
被 completed mix 带偏。

## 实验 A：saturation_throughput_12h

### 目的

这是吞吐提升的主证据。实验采用闭环固定并发，客户端保持固定 in-flight 数量，请求完成
后立刻补发下一条。策略更快时，在相同 4 小时内完成更多请求和 tokens。

这个实验对应此前 `hint_pressure_10h` 得到的结果：

```text
lru:          8040 requests, 1522.61 tok/s
shared_aware: 9460 requests, 1791.13 tok/s, +17.64%
family:       9270 requests, 1754.61 tok/s, +15.24%
```

新的 12h 版本保留闭环能力测试，同时加强压力、分段和公平性统计。

### Workload Mix

高压主段采用以下比例：

```text
durable_hot_family:        32%
sticky_session_followup:   18%
cold_rag_unique:           28%
transient_template_family:  10%
cold_rag_burst:             7%
decode_heavy:               5%
```

该组合让可复用 token 足够多，又保留冷 RAG、临时模板和 decode-heavy 噪声。它不是纯粹为
KVFabric 定制的理想场景；中小企业内部知识库、客服机器人、报表模板、agent workflow
都容易出现这种结构。

### 压力设置

```text
low_guard concurrency: 4
high_main concurrency: 16
red_burst concurrency: 20-22
max_in_flight: 与 concurrency 相同
max_tokens:
  durable/sticky: 32-96
  cold_rag: 32-96
  decode_heavy: 192-512
prompt_tokens:
  durable/sticky: 1800-3600
  cold_rag: 2200-3900
  transient: 1200-2800
```

若 LRU 在 ORANGE 下仍然没有持续 waiting queue，可把 high concurrency 提到 18，red
burst 提到 24。若 LRU 出现连续 timeout storm，回退到 14/18。

### 通过标准

强通过：

```text
best KVFabric high_main goodput_tok_s >= LRU * 1.30
p95 latency <= LRU * 1.05
rebuilt_from_eviction <= LRU * 0.45
errors == 0
low_guard non-regression pass
```

基础通过：

```text
best KVFabric high_main goodput_tok_s >= LRU * 1.15
p95 latency <= LRU * 1.10
rebuilt_from_eviction <= LRU * 0.60
errors == 0
low_guard non-regression pass
```

如果 uplift 在 20%-30% 之间，报告中写成“明显吞吐收益，尚未达到 30% 强目标”。

## 实验 B：enterprise_mixed_trace_12h

### 目的

这是“真实网关/企业混合流量”的稳定性实验。它采用 open-loop deterministic trace。
请求按时间戳到达，服务端更快不会自动收到更多请求。

开环 trace 在压力不足时 tok/s 接近相同，这是合理结果。此时主要看：

```text
p95/p99 latency
timeout/SLO miss
queue backlog
rebuilt_from_eviction
evicted blocks
admission saved blocks
prefix hit tokens by class
```

### Workload Mix

```text
interactive_chat_short:      20%
enterprise_rag_hot_doc:      20%
enterprise_rag_cold_doc:     22%
agent_tool_loop:             15%
summarization_or_extract:    10%
code_or_structured_output:    8%
decode_heavy_generation:      5%
```

### 到达过程

使用 deterministic trace，但到达间隔采用 bursty 形态：

```text
low_guard: 0.08-0.12 req/s, max_in_flight 16
high_main: 0.26-0.34 req/s, max_in_flight 48
red_burst: high_main 的 1.25x-1.40x, max_in_flight 64
```

如果校准显示 LRU 仍然低压，优先提高 burst factor 和 max_in_flight，其次提高 steady
target_rps。

### 通过标准

强通过：

```text
low_guard non-regression pass
high_main goodput_tok_s >= LRU * 1.10
high_main p95 latency <= LRU
red_burst timeout rate <= LRU * 0.70
rebuilt_from_eviction <= LRU * 0.50
```

基础通过：

```text
low_guard non-regression pass
high_main p95 latency <= LRU * 1.05
red_burst timeout rate <= LRU
rebuilt_from_eviction <= LRU * 0.60
```

这个实验不把 30% tok/s 作为硬目标。开环负载的主要价值是证明真实混合压力下的稳定性和
tail latency。

## 实验 C：sticky_conversation_trace_12h

### 目的

这个实验模拟长上下文多轮对话。真实 Chat Completion 多轮调用通常每一轮都重新提交完整
历史，因此后续 turn 与前一轮共享很长 prefix。KVFabric 应在这里体现 prefix reuse、
session/family 保护和 scheduler affinity 的价值。

正式实验使用 frozen transcript，不在线让模型自己和自己实时对话。实时 self-play 会让
三种策略生成不同历史，A/B 公平性很难保证。可以提前用模型生成 transcript，再冻结成
trace。

### Workload Mix

```text
sticky_support_session:    38%
sticky_agent_session:      24%
sticky_rag_followup:       18%
long_doc_followup_qa:      10%
one_shot_cold_noise:       10%
```

### Session 结构

```text
sessions: 300-600
turns per session: 8-24
system/tool prefix: 512-1400 tokens
history growth: 每轮增加 180-600 tokens
prompt cap: 4096 tokens
inter-turn gap:
  low_guard: 30-180s
  high_main: 5-45s
  red_burst: 1-15s
```

同一 session 的后续 turn 在 high_main/red_burst 中更密集，制造真实的 cache locality。
同时保留 10% one-shot cold noise，观察策略是否过度偏向 sticky 会话。

### 压力设置

```text
low_guard target_rps: 0.06-0.10
high_main target_rps: 0.22-0.32
red_burst target_rps: high_main 的 1.30x
max_in_flight:
  low_guard: 16
  high_main: 48
  red_burst: 64
```

如果 open-loop 难以把 LRU 压到 ORANGE，可切换为 closed-loop session scheduler：

```text
active sessions: 64
per-session next-turn delay: 1-20s
global max_in_flight: 48-64
```

### 通过标准

强通过：

```text
high_main prefix_hit_tokens >= LRU * 1.30
high_main goodput_tok_s >= LRU * 1.15
p95 latency <= LRU
rebuilt_from_eviction <= LRU * 0.45
one_shot_cold_noise latency <= LRU * 1.10
```

基础通过：

```text
high_main prefix_hit_tokens >= LRU * 1.15
high_main goodput_tok_s >= LRU * 1.08
p95 latency <= LRU * 1.05
rebuilt_from_eviction <= LRU * 0.60
```

## 最终报告结构

正式报告按下面顺序写：

1. 实验环境和 git commit。
2. 三组 workload 的 trace/config hash。
3. 压力校准结果，说明 ORANGE/RED 参数来源。
4. low_guard non-regression 表。
5. high_main goodput/latency 表。
6. red_burst 稳定性表。
7. KV cache lifecycle 证据表。
8. request class/session/family 分布审计。
9. 失败或未达到 30% 的原因分析。

核心图表：

```text
goodput_tok_s by policy and experiment
p95/p99 latency by segment
rebuilt_from_eviction by policy
prefix_hit_tokens by request class
admission_saved_blocks and scheduler_defers over time
completed request mix audit
```

## 实施清单

短期需要补齐的脚本能力：

1. 新增 `qwen3_5_27b_saturation_throughput_12h.json`。
2. 新增 `qwen3_5_27b_sticky_conversation_trace_12h.json`。
3. trace generator 支持 `warmup`、`low_guard`、`high_main`、`red_burst` segment。
4. load generator 在每条请求输出中记录 segment、class、session、family、prompt_tokens、
   output_tokens、SLO 状态。
5. summary 脚本按 segment 计算 goodput、latency、timeout、class mix 和 token mix。
6. 远程 launcher 支持统一 12h 三实验入口和校准入口。
7. 提交时保留 summary、sample、rolling metrics、Prometheus summary、lifecycle metrics 和
   job log，不提交完整 `kvfabric_lifecycle.jsonl`。

## 当前判断

这三组实验分工明确：

- `saturation_throughput_12h` 用来证明吞吐提升，压力可以大胆压到 LRU 接近饱和。
- `enterprise_mixed_trace_12h` 用来证明真实混合流量下的稳定性和 tail latency。
- `sticky_conversation_trace_12h` 用来证明长上下文多轮会话中的 prefix reuse 收益。

如果只保留两组，优先保留 A 和 C。A 给吞吐主证据，C 给长上下文场景主证据。B 适合作为
真实化补充和答辩时的稳定性证据。
