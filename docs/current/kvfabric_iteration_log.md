# KVFabric vLLM Prototype Iteration Log

本文记录从探针插入、策略接入到压力实验的完整迭代过程。尝试从“OS-style KV Cache resource management”的建议出发，逐步收敛到一个可复现、可解释、能在真实 vLLM 控制面运行的 prototype。

本文件为“日志”形态，记录了多次迭代的历程：

```text
V0-V8: 从探针到策略闭环
V9: family_protect 热路径优化
V9.1: low-KV 复测
V10: 普通场景无害 + 模板/多轮收益验证
当前入口 / 覆盖情况 / 对外表述 / 下一步
```

## 阶段锚点

### 2026-05-31：探针与封装初步完成

这一天对应项目从纯 Python 合成闭环进入真实 vLLM 控制面的节点。阶段产出包括：

- 初步完成 `kvfabric_lifecycle.py`；
- 在 `BlockPool`、`KVCacheManager` 等路径加入 lifecycle 探针；
- 建立 block/request 级 JSONL 事件流；
- 完成 lifecycle side table 的基础封装；
- 初步具备 prefix lookup、block sealed、touch、evict、rebuilt-from-eviction 的观测能力。

该节点可概括为：

```text
设计和合成验证 -> 真实 vLLM 控制面探针与封装
```

对应日志见 [logs/2026-05-31.md](../../logs/2026-05-31.md)。

### 2026-06-07：长时间对话压测与策略验证完成

这一天对应项目从“能观测”进入“初步策略可运行并通过代表性测试”的节点。阶段产出包括：

- 完成长时间对话压测程序设计与实现；
- 接入并验证 `shared_aware`、`family_protect` 和 admission control；
- 完成普通无共享、模板 family、cache pressure 等 workload 的初步 A/B；
- 将 lifecycle JSONL、Prometheus metrics 和 A/B comparison 接到同一套解释链路。

该节点可概括为：

```text
探针和封装 -> 长对话压测 + 策略原型初步验证
```

对应日志见 [logs/2026-06-07.md](../../logs/2026-06-07.md)。

### 2026-06-15：远程大规模实验准备

这一天对应项目从本地短验证进入远程长周期实验的节点。阶段产出包括：

- 确定在 2 x RTX 3090 服务器上开展实验，由周家润主要负责远程部署、运行和结果同步；
- 选择 Qwen3.5-9B 作为后续主实验模型，同时保留 Qwen3.5-27B 的探索和对比价值；
- 计划重跑早期 A/B、长对话和压力实验，方便后续代码迭代对照；
- 开始把 deploy、runner、sync、summary 和 run root 归档串成远程实验闭环。

该节点可概括为：

```text
本地策略验证 -> 远程 9B/27B 长周期实验准备
```

对应日志见 [logs/2026-06-15.md](../../logs/2026-06-15.md)。

### 2026-06-22：指标、请求模型与调试工具成型

6 月 15 日至 6 月 22 日，项目围绕远程实验暴露的问题补齐指标和工具链。阶段产出包括：

- 将 workload 从人工 hot/cold prompt 扩展为 tenant、family、session、turn、phase 和 request class 组成的 trace；
- 使用 `scheduled_at_seconds` 做 open-loop replay，降低 A/B 对比中的 workload drift；
- 增加 e2e、class、segment、SLO goodput、rebuilt-from-eviction 和 lifecycle summary；
- 完成远程 runner、结果同步、duration loadgen、trace loadgen 和 summary 工具。

该节点可概括为：

```text
远程能跑 -> 远程实验可解释、可复现
```

对应日志见 [logs/2026-06-22.md](../../logs/2026-06-22.md)。

### 2026-06-29：批量实验、dashboard 与最终 12h 矩阵

6 月 22 日至 6 月 29 日，周家润在远程服务器上进行了批量实验，并根据结果推动代码迭代。阶段产出包括：

- 重构 admission 进入位置，减少 cold / burst 请求进入 cache 后立即驱逐造成的 churn；
- 在 scheduler 中引入 hit-aware promotion、age guard、defer cap 和 latency-protected class；
- 修复 SLO、session、turn、request class 和 hint 的 header plumbing；
- 增加 run state、heartbeat、rolling class metrics、dashboard 和 lifecycle replay；
- 设计最终 12h 实验矩阵，覆盖高压吞吐、企业混合流量、多轮长对话和低复用保护。

该节点可概括为：

```text
中等规模调参 -> 可验收的 12h 长测矩阵
```

对应日志见 [logs/2026-06-29.md](../../logs/2026-06-29.md)。

### 2026-06-30 至 2026-07-01：期末汇报材料整理

这一阶段把代码设计、实验过程和结果整理为汇报材料。阶段产出包括：

- 梳理当前代码设计与相对 vLLM 的改进；
- 按远程实验暴露的问题整理接手后的主要迭代；
- 说明 Qwen3.5-9B 实验中的请求组成、发送方式、指标口径和验证目标；
- 从最终 12h 矩阵中挑选可解释、可复查的结果展示。

对应日志见 [logs/2026-06-30_2026-07-01.md](../../logs/2026-06-30_2026-07-01.md)。

## 0. 背景和目标

老师的核心意见是：KVFabric 不应只被表述为“改 vLLM 的 KV cache 策略”，而应被抽象成面向模型原生 OS 的 inference memory manager。当前交付重点是在 vLLM Python 控制面完成最小闭环，保持底层执行路径稳定：

```text
workload -> lifecycle side table -> policy -> metrics -> A/B comparison
```

对应到 OS 类比：

| OS 概念 | KVFabric 对应物 |
|---|---|
| physical page | KV block |
| page table | request block table |
| page sharing | prefix cache sharing |
| ref count | KV block ref count |
| page replacement | KV block eviction |
| page fault / reload | prefix miss / recompute |
| working set | active prompt/context blocks |
| admission control | 是否把冷长尾 block 放入 prefix cache |

本轮工作的短期目标是：先把真实 vLLM 的 block pool 接入 lifecycle side table，再逐步实现 shared-aware eviction、family protection 和 cache admission control，并用 pressure workload 对比 LRU。

## 1. V0: Lifecycle Probe 和 JSONL 事件流

### 改动

新增：

```text
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
experiments/prebenchmark_validation/examples/summarize_kvfabric_lifecycle.py
```

接入：

```text
vllm/v1/core/block_pool.py
vllm/v1/core/kv_cache_manager.py
```

事件包括：

```text
prefix_lookup
block_allocated
block_sealed
block_touched
ref_count_changed
block_evicted
```

环境变量：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
```

### 意义

这一版还没有改变策略，只是把 vLLM 内部的 KV block 生命周期变成可观测对象。它对应老师说的“把 KV cache 抽象为一等 OS 资源”：只有先有 side table 和事件流，后续才能讲生命周期、共享、重算代价和驱逐质量。

## 2. V1: Shared-Aware Eviction 初版

### 改动

在 `KVFabricLifecycleTracker` 中加入 retain score：

```text
retain_score =
  hit/share/reuse value
  + prefix anchor value
  + recompute value
```

在 `BlockPool.get_new_blocks()` 中，当 `KVFABRIC_EVICTION_POLICY=shared_aware` 时，不再直接按 vLLM free queue/LRU 顺序拿 block，而是对候选 block 做排序，优先选择 retain score 低的 block。

### 早期问题

第一次跑 `prefix_reuse_smoke` 和 `medium_prefix_reuse` 后发现：

| Workload | Policy | Prefix hit rate | Evicted blocks | Ranking events | Requests/s |
|---|---|---:|---:|---:|---:|
| prefix_reuse_smoke | LRU | 0.5079 | 0 | 0 | 3.96 |
| prefix_reuse_smoke | shared_aware | 0.5079 | 0 | 7 | 2.13 |
| medium_prefix_reuse | LRU | 0.9459 | 0 | 0 | 6.63 |
| medium_prefix_reuse | shared_aware | 0.9459 | 0 | 204 | 6.61 |

这说明功能通了，但策略在没有 eviction 的场景里也做 ranking，属于纯开销。用户指出“负优化”是正确的。

## 3. V1.1: 无压力快路径

### 改动

给 vLLM 的 `FreeKVCacheBlockQueue` 增加：

```python
peek_left_n(n)
```

在 `BlockPool.get_new_blocks()` 中先查看 LRU 队头将要拿走的 N 个 block：

```text
如果这些 block 都没有 block_hash，说明是真空闲 block，不会触发 prefix cache eviction
=> 直接走原始 popleft_n()

只有队头里存在 cached block 时
=> 才启用 KVFabric ranking
```

同时把全量排序改为 `heapq.nsmallest(num_blocks, ...)`，只选需要的前 N 个 victim。

### 结果

复测 `medium_prefix_reuse`：

| Policy | Prefix hit rate | Evicted blocks | Ranking events | Requests/s | Completion tok/s |
|---|---:|---:|---:|---:|---:|
| LRU | 0.9459 | 0 | 0 | 6.6547 | 159.25 |
| shared_aware | 0.9459 | 0 | 0 | 6.6584 | 159.34 |

结论：无 pressure 时 KVFabric 退化回 LRU，不再制造负优化。

## 4. V2: Cache Pressure Workload

### 改动

`online_batch.py` 新增 `cache_pressure` 场景生成器。

新增配置：

```text
experiments/prebenchmark_validation/configs/cache_pressure_hot_cold.json
```

结构：

```text
16 rounds
每轮 3 个热点共享前缀请求
每轮 8 个冷长尾请求
热点请求约 674 input tokens
冷长尾请求约 918 input tokens
```

### 调参过程

最初的 `cold_repeat=56/48/40` 都因为 chat template 后 token 数超过 1024 而失败。后来用本地 tokenizer 实测长度，确定：

```text
cold_repeat=20
max prompt length ~= 919
max_tokens=8
```

这样不会超过 `MAX_MODEL_LEN=1024`。

### 初始 pressure 结果

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-04_203321_qwen2_5_0_5b_cache_pressure_hot_cold_kvfabric_ab
```

| Policy | Evicted blocks | Shared-anchor eviction ratio | Avg evicted retain score | Prefix hit rate | Requests/s |
|---|---:|---:|---:|---:|---:|
| LRU | 4334 | 0.002307 | 30.99 | 0.2040 | 13.21 |
| shared_aware | 4265 | 0.000000 | 18.84 | 0.2040 | 12.51 |

结论：

```text
shared-aware 确实减少了高价值/共享 block 的误驱逐；
但 Python ranking 仍带来约 5% 吞吐开销；
prefix hit rate 没有提升。
```

## 5. V2.1: 修正 Retain Score

### 问题

旧 retain score 会把“很深但从未复用的冷长尾 block”也保护起来，因为 prefix depth 和 recompute cost 对所有 block 都加分。这不符合目标：冷长尾虽然长，但没有复用证据，不应该和热点共享 block 一样被保护。

### 改动

新的 retain score 逻辑：

```text
reused = hit_count > 0 or share_degree > 1

如果 reused:
  计入 hit_count/share_degree/branch_factor
  计入 anchor value
  计入 recompute value

如果没有 reused:
  retain_score 基本为 0
```

### 结果

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-04_204258_qwen2_5_0_5b_cache_pressure_hot_cold_kvfabric_ab
```

| Policy | Evicted blocks | Shared-anchor eviction ratio | Avg evicted retain score | Prefix hit rate | Requests/s |
|---|---:|---:|---:|---:|---:|
| LRU | 4334 | 0.002307 | 0.0979 | 0.2040 | 12.53 |
| shared_aware | 4265 | 0.000000 | 0.0000 | 0.2040 | 12.17 |

结论：eviction quality 更干净，但 prefix hit rate 仍未提升。

## 6. V3: Multi-Hot Pressure

### 动机

单热点 hot/cold 场景里，热点结构太简单；为了模拟多个长期热点族，新增：

```text
experiments/prebenchmark_validation/configs/cache_pressure_multi_hot.json
```

结构大致为：

```text
多个 hot family
每个 family 跨多个 cycle 回访
每次 hot 后插入 cold pressure 请求
```

### 结果和判断

multi-hot 能制造更多 eviction，但早期版本仍主要体现为 eviction quality 改善，prefix hit rate 没有稳定拉开。说明“只改 victim selection”还不够，冷长尾进入 prefix cache 后仍会污染 free queue，需要 admission control。

## 7. V4: Family-Protect Eviction

### 改动

在 `KVFabricLifecycleTracker` 中增加 protected 判断：

```text
hit_count >= protect_min_hit_count
or share_degree >= protect_min_share_degree
or branch_factor >= protect_min_branch_factor
```

`family_protect` 策略使用 hard bucket：

```text
未 hash / 真空闲 block
  -> 最先拿
普通 cached block
  -> 可驱逐
protected cached block
  -> 最后考虑
```

### 结果

相比 shared-aware，family_protect 逻辑更清楚，能够把 protected/shared-anchor 误驱逐压到 0；但 Python ranking 仍然带来端到端开销，尤其在候选窗口大、ranking events 多时明显。

## 8. V5: Admission Control 初版

### 动机

只在 eviction 阶段选 victim 仍然太晚。冷长尾已经进入 prefix cache 后，会制造大量缓存污染。因此加入 admission control：不要让所有冷长尾 full blocks 都进入 prefix cache。

### 初版策略

当 free ratio 较低时，只允许 request 的前若干 anchor blocks 进入 prefix cache：

```text
KVFABRIC_ADMISSION_MIN_FREE_RATIO
KVFABRIC_ADMISSION_ANCHOR_BLOCKS
```

### 问题

初版 admission 太激进，误伤热点族首次出现时的完整缓存，导致后续回访可命中的 token 变少，prefix hit rate 下降。

结论：这是一轮失败但有价值的迭代，说明 admission 必须 request-aware，而不是只看全局 free ratio。

## 9. V5.1: Request-Aware Admission

### 改动

记录每个 request 的 `prefix_lookup` 结果：

```text
request_prefix_hits[request_id] = hit_tokens
request_prompt_tokens[request_id] = prompt_tokens
```

策略：

```text
已经 prefix hit 的请求允许完整缓存；
没有 hit 的长冷请求，在低 free ratio 下限制缓存 block 数；
短请求不限制。
```

### 结果

request-aware admission 比初版稳，但阈值仍敏感。后续改为 length-aware admission：只对足够长、且没有复用证据的请求施加限制。

## 10. V5.2: Length-Aware Admission

### 改动

新增：

```text
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

逻辑：

```text
prompt_tokens < min_prompt_tokens:
  不限制

request 有 prefix hit 且 free_ratio 仍安全:
  不限制

否则:
  最多缓存 admission_anchor_blocks
```

### 结果 A: anchor_blocks=8

过于激进，会减少可复用热点的完整缓存。

### 结果 B: anchor_blocks=24

更稳，能够减少冷长尾污染，同时不明显伤害热点回访。后续实验默认使用：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

## 11. V6: 探针接回 A/B 和高压复测

### 动机

先前已经加入了很多 Prometheus 探针，但策略实验主要使用 `kvfabric_lifecycle.jsonl`，导致 feasibility report 中要求的 TTFT、TPOT、metadata overhead、block lifetime、recompute cost 等指标没有进入最终 A/B 对比。

### 改动

补齐：

```text
vllm_baseline/scripts/read_metrics.sh
experiments/prebenchmark_validation/examples/compare_kvfabric_ab.py
```

把以下 Prometheus 指标接入报告：

```text
request_hit_rate
prefix_token_hit_rate
saved_prefill_tokens_proxy
ttft_seconds_avg
tpot_seconds_avg
e2e_latency_seconds_avg
kv_block_lookup_hit_rate
kv_metadata_update_time_seconds_avg
kv_block_recompute_cost_tokens_avg
kv_block_eviction_regret_rate
```

### Hot/Cold 高压复测

在 hot/cold 压力下，family_protect + length-aware admission 能显著降低 evicted blocks 和 shared-anchor eviction，但 prefix hit tokens 未必变化。

典型结果中：

```text
evicted blocks: 4334 -> 74
shared-anchor eviction ratio: 0.002307 -> 0
requests/s: 12.5330 -> 12.6805
```

解释：这组证明缓存污染减少、被驱逐 block 的平均价值下降、管理开销没有变差；但不能把它解释成“前缀复用能力显著提升”，因为 saved prefill tokens 没变。

## 12. V7: Phased Hot Revisit 和消融实验

### 动机

上一版 `cache_pressure_hot_revisit.json` 虽然制造了大量 eviction，但 LRU 的 `protected_eviction_ratio` 仍为 0。这说明 workload 只是“高压”，没有真正打中 feasibility report 里关心的链路：

```text
hot warmup -> cold pressure evicts hot prefix -> hot revisit pays recompute
```

因此新增：

```text
experiments/prebenchmark_validation/configs/cache_pressure_phased_hot_revisit.json
```

结构：

```text
先 warmup 热点共享前缀
再插入大量冷请求冲刷 cache
最后 revisit 热点
```

### A/B 结果

典型结果：

```text
LRU:
  rebuilt-from-eviction blocks = 47
  prefix hit tokens = 7680

family_protect:
  rebuilt-from-eviction blocks = 0
  prefix hit tokens = 8432
```

这比“evicted blocks 降低”更接近 feasibility report 中的目标：减少无效驱逐和重算，并让收益在请求级指标中可见。

### 消融实验

加入：

```text
KVFABRIC_RETAIN_ABLATION=reuse
KVFABRIC_RETAIN_ABLATION=prefix
KVFABRIC_RETAIN_ABLATION=recompute
```

先做 family_protect 消融，发现 hard bucket 太强：只要一个 block 被判定为 protected，软分数因子关闭与否不会明显改变结果。

## 13. V7.1: Shared-Aware 软分数消融

### 动机

为了真正验证 retain score 的 `reuse/share`、`prefix position`、`recompute cost` 三类信号，需要在没有 hard bucket 的 `shared_aware` 策略下做消融。

### 结果

在 phased hot revisit 中：

```text
shared_only_reuse
shared_only_prefix
shared_only_recompute
```

三者都能把热点共享 anchor 从冷块里区分出来。说明 feasibility report 里的三类信号都有价值；但当前 workload 区分度太高，无法证明哪一个因子最强。

### 下一步推论

需要构造“混淆候选池”：

```text
冷块也拥有较深 prefix / 较高 recompute cost；
热点块拥有真实 share/reuse；
观察策略是否能区分短期看起来热和真正长期复用。
```

## 14. V8: Ambiguous Hot Revisit 和候选窗口优化

### 动机

前面的 phased hot revisit 能证明热点被冷压力驱逐后会产生 rebuild，但冷热区分太明显。为验证策略不只是“保护深 prefix”，新增：

```text
experiments/prebenchmark_validation/configs/cache_pressure_ambiguous_hot_revisit.json
```

这组 workload 的关键是：

```text
冷族内部也有短期共享 anchor；
冷块也表现出较深 prefix 和较高 recompute cost；
但冷族不会长期回访；
热点族才会经历 warmup -> cold pressure -> revisit。
```

### 初始 ambiguous A/B

在 0.5B 上，family_protect 能改善 eviction quality，但吞吐收益不稳定。调保护阈值后发现：

```text
KVFABRIC_PROTECT_MIN_HIT_COUNT=3
```

能避免过早保护短期冷族，同时保留真正多次复用的热点。

### 候选窗口优化

尝试：

```text
KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN=256
KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN=512
KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX=256
```

结论：窗口过大时 Python ranking 开销明显；需要后续把 family_protect 从 retain-score ranking 改成更轻的 protected deferral。

## 15. V9: Family-Protect 线性热路径优化

### 问题

在 qwen3.5-2B 的 `cache_pressure_ambiguous_hot_revisit` 压测中，旧版 `family_protect` 能把 LRU 误驱逐的 4 个热点 block 保护住：

```text
rebuilt_from_eviction_blocks: 4 -> 0
shared_anchor_eviction_ratio: 0.008282 -> 0
prefix_hit_tokens: 5440 -> 5984
```

但端到端吞吐仍是负优化。复盘后主要原因是实现成本太高：为了保护极少数热 block，Python 层反复对候选窗口做 retain-score 排序和候选日志展开。

### 改动

新增轻量选择器：

```text
KVFabricLifecycleTracker.select_family_protect_candidates()
```

逻辑：

```text
1. 保持 free queue / LRU 的原始顺序。
2. 遇到未保护 block，直接选作 victim。
3. 遇到 protected block，先 deferred。
4. 只有窗口里普通 block 不够时，才回退驱逐 protected block。
```

`BlockPool.get_new_blocks()` 的逻辑变成：

```text
无 cached eviction: 原始 popleft_n 快路径
shared_aware: retain-score ranking
family_protect: linear protected-victim deferral
```

同时新增：

```text
KVFABRIC_RANK_LOG_CANDIDATES=1
```

默认不再为每次 victim selection 写入前 16 个候选的详细 JSON payload，只保留聚合计数。

### qwen3.5-2B 复测结果

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-05_162643_qwen3_5_2b_cache_pressure_ambiguous_hot_revisit_kvfabric_ab
```

环境：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
KVFABRIC_PROTECT_MIN_HIT_COUNT=3
```

| Metric | LRU | family_protect linear | Change |
|---|---:|---:|---:|
| Requests/s | 3.4232 | 3.4568 | +0.98% |
| Avg latency | 0.2918s | 0.2892s | -0.91% |
| TTFT avg | 0.1686s | 0.1666s | -1.18% |
| E2E latency avg | 0.2895s | 0.2872s | -0.81% |
| Evicted blocks | 483 | 479 | -0.83% |
| Avg evicted retain score | 0.4452 | 0.0000 | -100% |
| Shared-anchor eviction ratio | 0.008282 | 0.000000 | -100% |
| Rebuilt-from-eviction blocks | 4 | 0 | -100% |
| Prefix hit tokens | 5440 | 5984 | +10.0% |

### 阶段结论

这一版让 `family_protect` 第一次在 qwen3.5-2B 高压场景下同时满足：

```text
资源管理质量显著改善；
端到端性能不再负优化。
```

但它距离“端到端吞吐提升 30%”仍然很远，因为 workload 中 LRU 只误杀 4 个热点 block，可转化收益空间太小。

## 16. V9.1: Low-KV 容量复测

### 动机

为了验证“更紧的 KV cache 是否能放大收益”，新增 profile：

```text
vllm_baseline/profiles/qwen3_5_2b_lowkv.env
```

它复用 qwen3.5-2B 权重，只把：

```text
GPU_MEMORY_UTILIZATION: 0.80 -> 0.65
```

### 结果

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-05_163409_qwen3_5_2b_lowkv_cache_pressure_ambiguous_hot_revisit_kvfabric_ab
```

| Metric | LRU | family_protect linear | Change |
|---|---:|---:|---:|
| Requests/s | 3.4540 | 3.3298 | -3.60% |
| Evicted blocks | 579 | 575 | -0.69% |
| Shared-anchor eviction ratio | 0.006908 | 0.000000 | -100% |
| Rebuilt-from-eviction blocks | 4 | 0 | -100% |
| Prefix hit tokens | 5440 | 5984 | +10.0% |

### 结论

```text
降低 KV 容量确实增加了 eviction 数量，但没有增加 LRU 对热点前缀的误杀规模。
LRU 仍然只产生 4 个 rebuilt-from-eviction block，因此 KVFabric 的可转化收益空间仍很小。
更小 KV 容量反而增加了策略事件数量，使 Python-layer family_protect 再次变成端到端负优化。
```

所以，下一步不应继续盲目压 `GPU_MEMORY_UTILIZATION`，而应扩大“可长期回访的热点 family”数量，或把保护粒度从单 block 扩展为 prefix-family。

## 17. V10: 普通场景无害 + 模板/多轮场景收益验证

### 动机

结合前期调研结果，推测KVFabric 在长对话、相似多轮对话、模板化 prompt/RAG 模板中应该更有效。因此实验目标改为：

```text
普通场景不明显掉速；
特定 KV reuse 场景验证收益。
```

新增配置：

```text
experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
experiments/prebenchmark_validation/configs/template_family_revisit.json
experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

扩展 `online_batch.py`：

```text
unique_cold: 普通无共享请求
template_family_revisit: 多个长期模板 family warmup -> 冷请求冲刷 -> family revisit
template_family_revisit_cycles: 多周期冷压力/回访交替
```

### 普通无共享场景

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-05_164347_qwen3_5_2b_ordinary_unique_cold_kvfabric_ab
```

| Metric | LRU | family_protect | Change |
|---|---:|---:|---:|
| Requests/s | 3.2320 | 3.2224 | -0.30% |
| Prefix hit tokens | 0 | 0 | 0 |
| Rebuilt-from-eviction blocks | 0 | 0 | 0 |
| Eviction ranking events | 0 | 0 | 0 |

结论：

```text
普通无共享请求中，没有长期复用结构，KVFabric 不触发 family_protect ranking。
端到端吞吐差异为 -0.30%，基本可视为测量噪声级别。
```

### 模板 family 单周期回访

第一次使用 `KVFABRIC_PROTECT_MIN_HIT_COUNT=3` 时，LRU 和 family_protect 结果完全一样。事后检查发现，被 LRU 误驱逐的热点块 `hit_count=1`，所以阈值 3 对模板/多轮场景过严。

改用：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
```

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-05_165447_qwen3_5_2b_template_family_revisit_kvfabric_ab
```

| Metric | LRU | family_protect | Change |
|---|---:|---:|---:|
| Requests/s | 3.8651 | 3.9608 | +2.48% |
| TTFT avg | 0.1342s | 0.1280s | -4.63% |
| E2E latency avg | 0.2564s | 0.2501s | -2.44% |
| Evicted blocks | 491 | 451 | -8.15% |
| Shared-anchor eviction ratio | 0.081466 | 0.000000 | -100% |
| Rebuilt-from-eviction blocks | 40 | 0 | -100% |
| Prefix hit tokens | 21760 | 27200 | +25.0% |
| Prefix hit rate | 0.180746 | 0.225932 | +25.0% |

### 模板 family 多周期回访

Run:

```text
experiments/prebenchmark_validation/runs/2026-06-05_165959_qwen3_5_2b_template_family_revisit_cycles_kvfabric_ab
```

| Metric | LRU | family_protect | Change |
|---|---:|---:|---:|
| Requests/s | 3.3506 | 3.4288 | +2.34% |
| TTFT avg | 0.1714s | 0.1639s | -4.34% |
| E2E latency avg | 0.2964s | 0.2893s | -2.38% |
| Evicted blocks | 911 | 815 | -10.54% |
| Shared-anchor eviction ratio | 0.105379 | 0.000000 | -100% |
| Rebuilt-from-eviction blocks | 96 | 0 | -100% |
| Prefix hit tokens | 30464 | 43520 | +42.86% |
| Prefix hit rate | 0.155380 | 0.221972 | +42.86% |

### 阶段结论

这一轮比单纯追求“所有 workload 吞吐 30% 提升”更合理：

```text
普通无共享场景：
  KVFabric 不触发保护路径，吞吐基本不掉。

模板/相似多轮场景：
  LRU 会误驱逐长期模板 family 的共享 KV block；
  KVFabric 能将 rebuilt-from-eviction 从 40/96 降为 0；
  prefix hit tokens 提升 25%-42.86%；
  requests/s 出现 2.3%-2.5% 的端到端正收益。
```

仍需诚实说明：当前 qwen3.5-2B 本机 Python prototype 还没有达到端到端吞吐 30% 提升。但 feasibility report 中的场景假设被验证了：KVFabric 的收益确实集中在长对话、模板化、多轮相似请求这类存在长期 KV 复用结构的 workload，而普通场景可以退化为低开销路径。

## 18. 当前代码和脚本入口

### Overlay 文件

```text
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
vllm_workspace/overlay/vllm/v1/core/block_pool.py
vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py
vllm_workspace/overlay/vllm/v1/core/kv_cache_utils.py
```

### 应用 overlay

```bash
bash vllm_workspace/scripts/apply_to_worktree.sh
```

### 实验配置

```text
experiments/prebenchmark_validation/configs/cache_pressure_hot_cold.json
experiments/prebenchmark_validation/configs/cache_pressure_multi_hot.json
experiments/prebenchmark_validation/configs/cache_pressure_phased_hot_revisit.json
experiments/prebenchmark_validation/configs/cache_pressure_ambiguous_hot_revisit.json
experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
experiments/prebenchmark_validation/configs/template_family_revisit.json
experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

### A/B 脚本

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

### 汇总脚本

```bash
python experiments/prebenchmark_validation/examples/summarize_kvfabric_lifecycle.py \
  --input <run>/<policy>/kvfabric_lifecycle.jsonl \
  --output <run>/<policy>/kvfabric_lifecycle_metrics.json

python experiments/prebenchmark_validation/examples/compare_kvfabric_ab.py \
  <run-dir> \
  --candidate family_protect \
  --output <run-dir>/ab_comparison.md

python experiments/prebenchmark_validation/examples/compare_kvfabric_ablation.py \
  <run-dir> \
  --output <run-dir>/ablation_comparison.md
```

## 19. Feasibility Report 策略覆盖情况

对照 `docs/reports/feasibility_report.md`，当前覆盖情况如下。

### 已实现并跑过

| 报告策略/机制 | 当前状态 |
|---|---|
| 生命周期 side table / 元数据维护 | 已实现 |
| block 生命周期事件日志 | 已实现 |
| Prometheus 指标探针 | 已实现，并已接回 A/B |
| LRU baseline | 已跑 |
| 仅生命周期统计、不改驱逐策略 | 已通过 `KVFABRIC_EVICTION_POLICY=lru` 等价覆盖 |
| 生命周期价值评分驱逐 | 已通过 `shared_aware` 覆盖 |
| protected family / family_protect | 已实现并跑过 |
| 前缀位置因子 | 已纳入 retain score，并做过 only-factor 消融 |
| 共享度/历史复用因子 | 已纳入 retain score/protected 判断，并做过 only-factor 消融 |
| 重算代价因子 | 已纳入 retain score 和指标，并做过 only-factor 消融 |
| pressure workload | 已有 hot/cold、multi-hot、phased、ambiguous、template family |
| 混合冷热负载 | 已跑 |
| 多热点压力负载 | 已跑 |
| hot revisit 回访负载 | 已跑，能观察 rebuilt-from-eviction |
| 模板化/相似多轮负载 | 已跑 |
| 老探针 + JSONL 联合解释 | 已补齐 |

### 部分实现

| 报告策略/机制 | 当前状态 |
|---|---|
| 二阶段驱逐 | 当前实现了“无 cached eviction 时 fast path；需要 eviction 时 protected deferral/ranking”，但不是严格低水位二阶段 |
| 分叉结构重要性 | 只有 `branch_factor` 弱代理，没有真实共享树 |
| 共享后分叉 L1 | vLLM 原生严格 prefix cache 可自然共享完整前缀并追加新尾块，但未显式维护共享链/分支链 |
| 显存水位治理 | admission control 已有，但阈值仍是经验值 |
| 长对话真实压测 | `experiments/langtime_running_test` 已拉入，但尚未接成严格服务端 A/B |

### 尚未实现或尚未系统验证

| 报告策略/机制 | 当前状态 |
|---|---|
| Chunk 级部分重叠共享 L2 | 未实现 |
| 写时复制 CoW | 未实现 |
| 显式共享树 / prefix-family-level 管理 | 未实现 |
| prefix caching off/on/KVFabric 三组本底对照 | 未系统跑 |
| 高并发 4-16 实验矩阵 | 未充分跑，当前主要是 concurrency=1 |
| 更大模型或 RTX 3090 复跑 | 待复跑 |
| soft retain score 权重区分 | 已证明任一信号有效，但尚未证明哪个信号最强 |

### 阶段判断

按 feasibility report 的分层成功标准：

```text
基础成功：已完成。
中级成功：部分完成，已证明生命周期感知驱逐改善 eviction quality，并在 phased/template revisit 中转化为请求级收益。
完整成功：尚未完成，因为共享后分叉结构化管理、chunk 级共享、CoW 仍未实现。
```

## 20. 阶段成果与解释

KVFabric 的目标是优化 KV cache 作为 OS-style resource 的生命周期管理质量，并在适合的 workload 中把这种管理质量转化为 SLO goodput 或请求级延迟收益。

在普通无共享请求中，KVFabric 不触发保护路径，requests/s 仅 -0.30%，基本退化为低开销路径。

在模板化 prompt / 相似多轮场景中，LRU 会误驱逐长期模板 family 的共享 KV block；KVFabric 将 rebuilt-from-eviction 从 40/96 降为 0，将 prefix hit tokens 提升 25%-42.86%，并带来约 2.3%-2.5% 的端到端 requests/s 正收益。

## 21. 当前局限

1. 当前收益主要出现在 eviction quality、rebuilt-from-eviction、prefix hit tokens 和部分请求级指标上，不能泛化成所有 workload 的吞吐提升。
2. 策略是 Python-layer prototype，V9 已经降低 `family_protect` 热路径开销，但 side table 更新和 JSONL 事件流仍会消耗 CPU。
3. Admission threshold 目前是经验值：

```text
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

4. `family_protect` 的 hard bucket 太强，导致软分数消融无法区分三类因子谁更强。
5. 当前 protected 仍是 block-level，不是 prefix-family-level，也没有真实共享树和 CoW。
6. 当前主要是 concurrency=1，尚未充分验证高并发下的 TTFT p95 和吞吐。
