# KVFabric 当前代码设计与 vLLM 改进说明

日期：2026-06-30

本文面向期末汇报材料整理，目标是把当前仓库中已经落地的 KVFabric 代码设计讲清楚，并说明它相对原生 vLLM 0.22.1 的改进点。这里的“改进”主要指控制面能力、可观测性、策略可调度性和实验闭环能力，不等价于所有 workload 的 raw token/s 都提升。

## 1. 总体定位

KVFabric 是覆盖在 vLLM Python 控制面上的 KV Cache 生命周期管理层。它不重写模型执行 kernel，也不改变 vLLM PagedAttention 的底层张量布局；它把 vLLM 原本只用于分配、释放和 prefix cache lookup 的 KV block，提升为带生命周期状态、共享关系、重算代价、请求 hint 和调度反馈的系统资源对象。

可以把当前系统理解为三层：

| 层次 | vLLM 原生职责 | KVFabric 增加的职责 |
|---|---|---|
| KV block 数据面 | PagedAttention block 分配、ref count、prefix hash cache | 不改 tensor 数据面，只读取 block 生命周期事件 |
| 控制面资源管理 | LRU free queue，prefix cache 命中后 touch，空间不足时驱逐队头 cached block | lifecycle side table、retain score、family metadata、admission、eviction deferral |
| 服务与实验面 | OpenAI API、scheduler、Prometheus 基础指标 | hint headers、scheduler affinity、SLO/latency protection、JSONL 事件流、A/B summary、dashboard/replay |

当前 overlay 文件清单由 `vllm_workspace/upstream_manifest.txt` 维护，核心路径如下：

```text
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
vllm_workspace/overlay/vllm/v1/core/kvfabric_family.py
vllm_workspace/overlay/vllm/v1/core/kvfabric_hints.py
vllm_workspace/overlay/vllm/v1/core/block_pool.py
vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py
vllm_workspace/overlay/vllm/v1/core/single_type_kv_cache_manager.py
vllm_workspace/overlay/vllm/v1/core/kv_cache_coordinator.py
vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py
vllm_workspace/overlay/vllm/entrypoints/openai/engine/serving.py
vllm_workspace/overlay/vllm/tracing/utils.py
vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py
vllm_workspace/overlay/vllm/v1/metrics/stats.py
vllm_workspace/overlay/vllm/v1/metrics/loggers.py
```

## 2. 原生 vLLM 的 KV Cache 控制面

原生 vLLM 的 prefix caching 可以简化为以下流程：

1. 请求进入 scheduler，先计算 prompt 对应的 block hash。
2. `KVCacheManager.get_computed_blocks()` 根据 block hash 找最长已缓存前缀。
3. 命中的 cached block 被 `BlockPool.touch()` 提升 ref count，避免被正在使用时驱逐。
4. 未命中的 token 继续 prefill，需要新 KV block。
5. `BlockPool.get_new_blocks()` 从 free queue 取 block。free queue 中既有真正空闲 block，也有 ref count 为 0 但仍带 block hash 的 cached block。
6. 如果取出的 block 仍在 prefix cache hash map 中，就把它从 cache map 移除，等价于 LRU 驱逐。
7. 请求完成后 block ref count 归零，按顺序回到 free queue，之后可作为缓存候选或驱逐候选。

这个设计很高效，但原生控制面更偏“页分配器 + LRU cache”：

- block 没有显式生命周期状态机；
- 不记录一个 block 是否是长期共享主干；
- 不知道某次驱逐之后同 hash 是否被重建；
- 不区分 durable/hot、transient、cold、bypass 请求；
- admission 基本是“full block 能缓存就缓存”；
- scheduler 默认不根据 KV cache 复用价值调度等待队列；
- metrics 能看到 prefix cache 命中等总体信息，但难以解释为什么某类请求变快或变慢。

KVFabric 的核心工作就是在不破坏这些原生机制的前提下，给它补上 OS 风格资源管理控制面。

## 3. Lifecycle Side Table

核心文件：`kvfabric_lifecycle.py`

核心数据结构：

```text
LifecycleBlockMeta
  block_id
  block_hash
  prefix_depth
  ref_count
  hit_count
  share_degree
  branch_factor
  recompute_cost_tokens
  state
  family_id/root_hash/parent_hash
  family_hit_count/family_branch_count/family_regret_count
  protected_depth

EvictedShadow
  被驱逐 block 的 hash、深度、hit/share、重算代价、retain score、驱逐时间

RequestMeta
  request_id、prompt_tokens、prefix_hit_tokens、request_class、hint、defer/admission 计数等
```

side table 的状态大致可以按下面理解：

| 状态 | 含义 |
|---|---|
| `FREE` | 没有被请求占用，通常还没有有效 hash |
| `ACTIVE` | 正在被某个请求使用 |
| `SEALED` | full block 已写入 prefix cache |
| `SHARED` | 发生 prefix hit 或 ref count 大于 1 |
| `COOLING_WARM` | 请求释放，仍在 cache 中，但没有明显复用证据 |
| `COOLING_HOT` | 请求释放，仍在 cache 中，并且有 hit/share/family 证据 |
| `EVICTED` | 从 prefix cache 中被驱逐 |

相对 vLLM 的改进：

- vLLM 只需要知道 block 是否有 hash、ref count 是否为 0；KVFabric 记录 block 为什么有价值。
- vLLM 驱逐后不会记住“刚刚驱逐了谁”；KVFabric 用 `EvictedShadow` 记录被驱逐 hash，后续同 hash 再次 sealed 时标记 `rebuilt_from_eviction=true`。
- vLLM 不区分“深但一次性”的冷长尾和“浅但长期复用”的共享主干；KVFabric 的 retain score 和 protected 判断会优先看复用证据，再考虑 prefix 位置和重算代价。

## 4. JSONL 事件流

KVFabric 通过 `KVFABRIC_LIFECYCLE=1` 和 `KVFABRIC_LIFECYCLE_LOG_PATH` 启用 JSONL 事件流。主要事件包括：

```text
tracker_initialized
request_hints_observed
prefix_lookup
block_allocated
block_sealed
block_touched
ref_count_changed
cache_admission_limited
request_scheduled
request_deferred
request_promoted
request_latency_promoted
request_finished
eviction_candidates_ranked
block_evicted
lifecycle_reset
```

这些事件支撑了后续 `kvfabric_lifecycle_metrics.json`、summary、dashboard 和 replay。

相对 vLLM 的改进：

- vLLM 的日志和 Prometheus 指标更适合看总体吞吐、延迟和 cache hit；KVFabric 能解释某个 block/request/family 的生命周期。
- 可以从事件流直接统计 rebuilt-from-eviction、admission saved blocks、scheduler promotion、hint 覆盖率、warm-family hit rate。
- 可以把 KV cache 管理过程做成 replay 动画，用于展示 LRU 和 KVFabric 的驱逐差异。

## 5. Prefix Family 元数据

核心文件：`kvfabric_family.py`

vLLM 的 block hash 本身包含父 hash 和 block tokens，因此 block-aligned prefix 具有天然的链式关系。KVFabric 利用 `cache_full_blocks()` 中能够看到的当前 block hash、parent hash、root hash，构建轻量级 prefix family index：

```text
PrefixNodeMeta
  block_hash
  family_id
  root_hash
  parent_hash
  depth
  children
  hit_count/seal_count/evict_count/rebuild_count/regret_count

PrefixFamilyMeta
  family_id
  root_hash
  hit_count
  sealed_blocks
  evicted_blocks
  rebuilt_blocks
  regret_count
  max_depth
  protected_depth
```

它不是重写 vLLM 的 prefix trie，也不是实现 chunk 级任意共享；它是在原生 exact full-block prefix caching 之上建立的元数据索引。

相对 vLLM 的改进：

- vLLM 只按 hash 查 block；KVFabric 能知道一个 block 属于哪个 prefix family。
- 可以把“某个 family 多次命中”“某个 family 发生 regret/rebuild”“某个节点有 children”纳入保护判断。
- `protected_depth` 可以把 family 的浅层主干作为保护对象，而不是盲目保护所有深层尾块。

## 6. Hint 元数据与 OpenAI Serving 接入

核心文件：

```text
kvfabric_hints.py
entrypoints/openai/engine/serving.py
tracing/utils.py
```

KVFabric 从 OpenAI serving 请求头提取以下 hint：

```text
x-kvfabric-request-class
x-kvfabric-trace-request-id
x-kvfabric-tenant-id
x-kvfabric-family-id
x-kvfabric-cache-priority
x-kvfabric-expected-reuse
x-kvfabric-phase
x-kvfabric-burst
x-kvfabric-session-id
x-kvfabric-turn-index
x-kvfabric-slo-ms
x-kvfabric-hint-confidence
```

这些 hint 会被转换成 `KVFabricRequestHints`，再写入 request meta 和 hint family runtime。

典型含义：

| Hint | 用途 |
|---|---|
| request class | 区分 hot follow-up、cold RAG、decode-heavy、background 等 |
| tenant/family/session | 识别业务级 family 和多轮会话 |
| expected reuse | durable、transient、none、unknown |
| cache priority | high、normal、low、bypass |
| turn index | 多轮会话后续 turn 通常有更强复用价值 |
| SLO ms | scheduler 做 SLO-aware promotion/head guard |

相对 vLLM 的改进：

- vLLM 原生 OpenAI serving 不会把业务请求类型和 SLO 传到 KV cache 控制面。
- KVFabric 允许上层服务把“这个请求是否可能复用”“是否是低优先级冷请求”“是否接近 SLO”传给 admission 和 scheduler。
- hint 是可选的：`no_hints`、`partial_hints`、`full_hints`、`noisy_hints` 都可以在实验中模拟。

## 7. 统一 Controller

核心结构：`KVFabricControlConfig`

后期 9B 实验中，KVFabric 不再只用 `shared_aware`、`family_protect` 这种离散策略名表达系统状态，而是用连续控制向量：

```text
admission_strength
eviction_strength
scheduler_strength
slo_protection_strength
hint_trust
low_reuse_cache_fraction
transient_cache_fraction
bypass_cache_fraction
durable_cache_fraction
cold_cache_fraction
```

常见 profile：

| Profile / Policy | Admission | Eviction | Scheduler | 用途 |
|---|---:|---:|---:|---|
| `lru` / `off` | 0 | 0 | 0 | vLLM 行为对照 |
| `kvfabric_admission` | 高 | 低或 0 | 0 | 主吞吐 / SLO goodput |
| `kvfabric_throughput` | 高 | 中等 | 0 | prefill throughput proof |
| `kvfabric_rebuilt` | 中等 | 低 | 0 | rebuilt-from-eviction 下降验证 |
| `kvfabric_latency` | 视阶段而定 | 通常 0 | 高 | foreground latency protection |

相对 vLLM 的改进：

- vLLM 的策略基本由固定调度策略、prefix cache 开关和 LRU free queue 决定。
- KVFabric 可以把 admission、eviction、scheduler、SLO protection 分开调，避免一个实验策略同时改太多变量。
- 12h matrix 用 stage-local subshell 设置参数，保证吞吐 profile 不泄漏到 latency/guard stage。

## 8. BlockPool 接入与驱逐策略

核心文件：`block_pool.py`

主要接入点：

| 函数 | KVFabric 行为 |
|---|---|
| `__init__` | 从环境变量创建 `KVFabricLifecycleTracker` |
| `cache_full_blocks()` | sealed full block 时记录 hash、depth、parent/root、request id |
| `get_new_blocks()` | 在需要分配 block 时可选择 LRU、shared-aware、family-protect |
| `_maybe_evict_cached_block()` | 驱逐 cached block 时记录 `block_evicted` 和 shadow |
| `touch()` | prefix hit 后记录 hit/share/family touch |
| `free_blocks()` | ref count 变化时更新生命周期状态 |
| `reset_prefix_cache()` | 重置 side table |

关键优化：无压力快路径。

`get_new_blocks()` 先从 free queue 头部看即将被拿走的 `num_blocks` 个 LRU victim。如果这些 block 都没有 `block_hash`，说明它们是真空闲 block，不会驱逐 prefix cache，此时直接走原始 `popleft_n()`。只有队头 victim 中存在 cached block，且 retain score/protected 判断显示有必要时，才进入 KVFabric selector。

驱逐策略包括：

1. `lru`
   - 等价 vLLM 原始 free queue 顺序。
   - 可以同时启用 lifecycle 观测，但不改变 victim。

2. `shared_aware`
   - 对候选窗口计算 eviction retain score。
   - 低 retain score 的 block 优先被驱逐。
   - 支持 `rank` 和 `linear` selector。9B 上更偏向 `linear`，减少排序和 remove 开销。

3. `family_protect`
   - 不对全窗口排序，而是沿 LRU 顺序扫描。
   - 遇到 protected block 先放入 deferred。
   - 普通 block 足够时优先驱逐普通 block。
   - 候选不足时才回退驱逐 protected block。
   - 后期加入 soft budget，限制保护过强导致 cache 污染。

相对 vLLM 的改进：

- vLLM 的 LRU 不知道 block 的未来价值；KVFabric 可以跳过明显高价值的共享主干。
- vLLM 无法统计“误驱逐导致后面重算”；KVFabric 能把 rebuilt-from-eviction 作为直接指标。
- KVFabric 保留无压力快路径，避免没有 cached eviction 时为策略付额外成本。

## 9. Admission Control

核心文件：

```text
single_type_kv_cache_manager.py
kvfabric_lifecycle.py
```

vLLM 原生逻辑是在 `cache_blocks()` 中尽量把 full block 写入 prefix cache。KVFabric 在 `SingleTypeKVCacheManager.cache_blocks()` 中，在真正 cache full blocks 之前调用：

```text
block_pool.cache_pressure_snapshot()
kvfabric_lifecycle.limit_cache_blocks()
```

这一步不会拒绝请求，也不会少算模型输出；它只限制“新算出来的 full block 有多少写入 prefix cache”。低复用长尾仍然完成请求，只是不把所有尾部 block 都污染成未来缓存候选。

admission 判断综合：

- free ratio；
- LRU head window 中 hashed block 比例，即 eviction risk；
- request prompt tokens；
- request 是否已有 prefix hit；
- hint expected reuse / cache priority；
- durable、transient、low-reuse、bypass 的 cache fraction；
- discovery/anchor blocks。

连续 fraction 逻辑可以概括为：

```text
ADMISSION_STRENGTH = 0: 全缓存，退化为 vLLM
ADMISSION_STRENGTH = 1: 按请求类别 fraction 缓存
durable/high reuse: fraction 接近 1，完整缓存
low/bypass/cold: fraction 接近 0，只保留 discovery/anchor
```

相对 vLLM 的改进：

- vLLM 对一次性冷长 prompt 和长期复用 prompt 基本同等缓存。
- KVFabric 可以阻止 cold RAG、bypass、low-reuse 请求把 KV cache 填满。
- 9B 实验最终发现 admission 比强 eviction re-ranking 更适合作为主吞吐路径，因为它不在 allocation 热路径排序和移动 free queue。

## 10. Scheduler Affinity 与 Latency Protection

核心文件：`sched/scheduler.py` 与 `kvfabric_lifecycle.py`

KVFabric 在 FCFS waiting queue 上加入两类可选机制：

1. 冷 miss defer
   - 当 eviction risk 高、请求很长、没有 prefix hit、且不是 durable/hot hint 时，可以把该请求临时移到队尾。
   - 有 defer max count、max age、low-reuse age cap，避免饥饿。

2. positive / latency promotion
   - 在 waiting queue 前若干个请求中扫描。
   - 对 durable/high-reuse/session/turn/hit-aware 请求打分。
   - 对 latency protected classes 或接近 SLO 的请求进行 promotion。
   - 有 head age guard 和 SLO head guard，防止一直绕过队首请求。

后期 latency profile 进一步把普通 positive promotion 和 latency promotion 拆开：

```text
KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW
KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW
KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP
KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP
```

相对 vLLM 的改进：

- vLLM scheduler 主要从调度公平性和 token budget 角度工作，不知道请求是否更可能命中高价值 KV。
- KVFabric 可以在高压下优先服务可复用或前台交互请求，也可以为接近 SLO 的请求设置保护。
- 这带来明显 tradeoff：foreground latency 可以显著改善，但 background/decode 可能回退。因此最终文档必须按 request class 报告，而不能只看 overall。

## 11. Metrics 与 Prometheus 扩展

核心文件：

```text
kv_cache_metrics.py
metrics/stats.py
metrics/loggers.py
```

新增指标类型：

| 指标 | 用途 |
|---|---|
| block lookup queries/hits/time | prefix hash lookup 成本和命中 |
| block allocations/cached/evictions | block 生命周期总量 |
| free/total/active/peak active/cached entries | cache 容量与压力 |
| block lifetime / idle before evict / reuse gap | 驻留时间和复用间隔 |
| access count / peak ref count / cache depth | 被驱逐 block 的价值特征 |
| recompute cost tokens | 估算被驱逐后重算成本 |
| metadata update time | KVFabric 控制面开销 |
| request queue/inference/prefill/decode/e2e latency | 请求级延迟分解 |

相对 vLLM 的改进：

- vLLM 原始 metrics 更难回答“策略为什么有效”。
- KVFabric metrics 能把 prefix hit、rebuilt、admission、scheduler promotion 和用户可见 latency 对齐到同一份 summary。
- `read_metrics.sh`、summary 脚本和 dashboard 可以从 Prometheus 与 JSONL 两条路径交叉验证。

## 12. 实验工具链

当前仓库有三类实验入口：

1. `experiments/prebenchmark_validation/`
   - 早期 2B/0.5B 本地 smoke 和短 A/B。
   - 用于验证 hot/cold、template family、ordinary unique cold 等小场景。

2. `experiments/long_pressure_benchmark/`
   - 远程 2 x RTX 3090 长周期实验。
   - 支持 duration loadgen、trace generation、trace replay、remote deploy、summary、sync。

3. `dashboard/`
   - Streamlit 实时面板。
   - `kvfabric_run_reader.py` 读取 rolling metrics、Prometheus、lifecycle、trace、raw outputs。
   - `kv_cache_replay.py` 和 `render_replay_gif.py` 用于 KV cache 状态 replay。

相对 vLLM 的改进：

- vLLM 提供 benchmark 工具，但不直接提供 KV cache 生命周期策略 A/B 闭环。
- KVFabric 把 trace 生成、远程启动、结果同步、Prometheus 摘要、JSONL summary、SLO goodput、dashboard/replay 连成一套实验系统。

## 13. 与 vLLM 对比总表

| 维度 | vLLM 原生 | KVFabric 当前实现 |
|---|---|---|
| KV block 抽象 | 分配单位、prefix hash cache entry | 生命周期资源对象 |
| 生命周期状态 | 隐含在 ref count/hash/free queue 中 | side table 显式状态 |
| 驱逐策略 | free queue/LRU | LRU、shared-aware、family-protect、连续 eviction strength |
| 共享关系 | exact prefix hash 命中 | prefix family 元数据、family hit/branch/regret |
| 重算反馈 | 无直接 rebuilt-from-eviction 事件 | EvictedShadow + rebuilt 标记 |
| admission | full block 默认缓存 | hint-aware/pressure-aware fraction admission |
| 请求元数据 | 基本 request id/trace headers | tenant/family/session/class/reuse/priority/SLO hints |
| 调度 | FCFS/priority/token budget | positive affinity、defer、latency promotion、SLO guard |
| 指标 | prefix hit、吞吐、基础延迟 | lifecycle、rebuilt、admission、scheduler、e2e、per-class |
| 实验闭环 | benchmark 为主 | A/B、trace、duration、remote、summary、dashboard、replay |
| 默认安全性 | 原生行为 | KVFabric disabled 时保持原生；profile 分阶段打开 |

## 14. 当前边界与不能过度宣称的内容

已经实现并可汇报：

- vLLM Python 控制面上的 lifecycle side table；
- JSONL 事件流；
- Prefix Family 元数据；
- rebuilt-from-eviction 反馈；
- shared-aware / family-protect / admission / scheduler affinity；
- OpenAI serving hint headers；
- Prometheus 扩展指标；
- Qwen3.5-2B 本地 smoke 到 Qwen3.5-9B 远程长测闭环；
- dashboard/replay 工具链。

需要谨慎说明：

- 当前没有实现 chunk 级任意重叠共享。
- 当前没有实现真实 CoW。
- 当前没有改写底层 KV tensor 数据面。
- prefix family 是控制面元数据，不是完整替代 vLLM prefix cache 结构。
- 不是所有 workload 都提升。低复用、低频、普通混合流量的目标是低干预和不退化。
- latency profile 对 foreground interactive classes 有收益，但可能牺牲 background/decode，需要按 class 报告。

## 15. 汇报建议口径

可以这样表述：

> KVFabric 把 vLLM 中原本作为缓存页使用的 KV block 提升为可观测、可解释、可调度的生命周期资源。它不改变 vLLM PagedAttention 数据面，而是在 BlockPool、KVCacheManager、Scheduler、OpenAI serving 和 metrics 路径上加入轻量 overlay：记录 block 生命周期和 prefix family，识别错误驱逐后的重建，用 hint-aware admission 减少冷长尾污染，在需要时用 shared-aware/family-protect 保护共享主干，并用 scheduler affinity 保护可复用或前台交互请求。相对 vLLM 的 LRU prefix cache，KVFabric 的优势不是“所有请求都更快”，而是在有稳定共享前缀和容量竞争的场景中提高 KV cache 使用质量，在 SLO 边界上提升 goodput，并在普通/低复用场景保持低干预。
