# KVFabric 下一阶段源码修改与三人分工方案

本文档面向下一阶段真正修改 vLLM 源码。它基于当前仓库内较新的生命周期设计、源码分析、预基准验证、论文复现实验和最小闭环脚本，目标是把“已经能验证思想的合成闭环”推进到“在 vLLM Python 控制面中可运行、可观测、可 A/B 对比的原型”。

## 1. 当前项目状态判断

当前项目已经完成了四类前置工作。

第一，vLLM baseline 与实验入口已经具备。`vllm_baseline/` 可以完成模型下载、offline smoke、local serving、online 验证和日志摘要。`experiments/prebenchmark_validation/` 进一步提供了 `offline_batch`、`online_batch`、`prefix_reuse_smoke`、`medium_prefix_reuse`、`soak_prefix_reuse_20min` 等预验证入口。当前文档记录显示，在 `qwen3_5_2b`、`ENABLE_PREFIX_CACHING=1` 下，短共享前缀不足 full block 时 prefix hit 仍为 0；共享系统前缀拉长到约 716 input tokens 后，中等 prefix reuse 测试可观察到约 74.9% 的 prefix cache hit rate。这说明工具链已经能观察 vLLM prefix caching 的真实行为。

第二，基础性能与复现实验已经形成标准。`experiments/paper_reproductions/vllm_performance_benchmark/` 用于离线吞吐、prefix on/off A/B、KV cache usage 等指标采集。已有报告指出，在 8GB WSL2 环境中，显存和 KV cache 容量是主要瓶颈；无共享前缀时开启 prefix caching 可能是负收益；真正的收益必须来自共享 system prompt、RAG 公共文档、多轮历史等高复用场景。这直接决定了后续源码改造不能只追求“打开 prefix cache”，而要让系统知道哪些 block 值得保留。

第三，项目已经有一个纯 Python 的最小闭环：`experiments/benchmarks/lifecycle_policy/`。它覆盖合成负载、生命周期 side table、LRU 与 shared-aware 驱逐策略、指标和报告。这个闭环的价值是验证策略思想，但它没有接入 vLLM 的真实 block pool、request、scheduler 和 prefix cache，因此下一步应把其中成熟的元数据字段、评分思想、事件和指标迁移到 vLLM 控制面。

第四，源码切入点已经基本明确。`docs/research/code_research/vllm_v0_19_0_kv_cache_source_analysis.md` 已经确认 vLLM v0.19.0 的关键路径：`Request.update_block_hashes()` 维护 full-block 链式 hash；`KVCacheManager.get_computed_blocks()` 查询 prefix hit；`SingleTypeKVCacheManager.allocate_new_computed_blocks()` touch 命中 block；`BlockPool.get_new_blocks()` 从 free queue 取块并在必要时驱逐 prefix cache 身份；`BlockPool.cache_full_blocks()` 把 full block 放入 hash map；`BlockPool.free_blocks()` 在 ref count 归零后放回 free queue。初始阶段不应修改 CUDA/Triton kernel，也不应改 worker block table 的 append-only 语义。

因此下一阶段的核心判断是：

> 先把合成闭环中的生命周期观测、side table、共享关系和评分策略低侵入地接入 vLLM Python 控制面；先做到可观测、可关闭、可 A/B，再逐步改变驱逐候选选择。不要一开始做物理去重、真正 CoW、kernel 修改或非前缀 chunk 级复用。

## 2. 源码修改边界

短期修改范围应限制在 `KVFabric/vllm_workspace/overlay/` 中的 vLLM Python 控制面文件，再通过 `vllm_workspace/scripts/apply_to_worktree.sh` 应用到完整 `../vllm-v0.19.0` 工作树运行。

优先文件：

| 文件 | 当前职责 | 下一步改造职责 |
| --- | --- | --- |
| `vllm/v1/core/block_pool.py` | 全局 block 池、prefix hash map、free queue、驱逐 | 生命周期 side table、block sealed/touch/free/evict 事件、候选评分、evicted shadow |
| `vllm/v1/core/kv_cache_manager.py` | scheduler 侧 KV cache 主接口 | request 级 prefix lookup 事件、num_cached_tokens 与 hit tokens 记录 |
| `vllm/v1/core/single_type_kv_cache_manager.py` | per-request block list、touch、allocate、free、cache | request -> block 生命周期关联、释放时 cooling 状态判断 |
| `vllm/v1/core/sched/scheduler.py` | 请求调度主循环 | request admitted/scheduled 指标、后续接收 lifecycle hint |
| `vllm/v1/core/kv_cache_metrics.py` | block residency 指标 | 承接生命周期指标或汇总接口 |
| `vllm/v1/metrics/stats.py` | prefix cache 与 scheduler stats | 增加 summary 级生命周期指标 |

暂不修改：

- CUDA/Triton attention kernel；
- worker 侧 `BlockTables` 的 block id 语义；
- 已下发给 worker 的 block table；
- 物理 block 去重、迁移、真正的写时复制；
- 非严格前缀的任意 chunk 命中。

这个边界的原因很具体：vLLM 当前允许相同 hash 对应多个物理 block，但不会把新 block 替换成已有 block，因为 worker 使用 append-only block ID 序列生成 slot mapping。初始阶段若改变物理 ID 或 KV cache slot 语义，正确性风险会迅速超过课程项目可控范围。

## 3. 推荐实施路线

### L0：观测层，不改变 vLLM 行为

这是第一步源码修改，必须先完成。目标是关闭开关时与 vanilla vLLM 行为一致；打开开关时只写 JSONL 事件和 summary，不改变任何调度或驱逐决策。

建议新增一个轻量模块，例如：

```text
vllm/v1/core/kvfabric_lifecycle.py
```

其中包含：

- `LifecycleBlockState`：`MUTABLE_TAIL`、`INDEXED`、`SHARED_ACTIVE`、`COOLING_HOT`、`COOLING_WARM`、`CANDIDATE`、`EVICTED`、`REBUILT`；
- `LifecycleBlockMeta`：block id、block hash、family id、prefix depth、ref count、hit count、share degree、branch factor、last access、retain score；
- `PrefixFamilyMeta`：family id、root hash、children、family hit count、branch factor；
- `EvictedShadow`：evicted hash、family、depth、evict time、retain score、pressure level；
- `LifecycleEventLogger`：受环境变量控制的 JSONL writer。

建议环境变量：

```text
KVFABRIC_LIFECYCLE=0/1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kv_lifecycle_events.jsonl
KVFABRIC_LIFECYCLE_POLICY=observe
```

L0 需要打点的位置：

- `KVCacheManager.get_computed_blocks()`：记录 `prefix_lookup`，字段包括 request id、prompt tokens、hit tokens、skip flag、max hit length。
- `BlockPool.cache_full_blocks()`：记录 `block_sealed`，字段包括 block id、block hash、parent hash、prefix depth、group id。
- `BlockPool.touch()`：记录 `block_touched`，更新 hit count、last access、share degree；如果 ref count 从 0 变为 1，要记录它从 free queue 回到 active。
- `BlockPool.free_blocks()`：记录 `cooling_transition`，ref count 归零后先按元数据标记为 hot/warm/candidate。
- `BlockPool._maybe_evict_cached_block()`：记录 `block_evicted`，保存 shadow 元数据，随后 reset hash。
- `Scheduler.schedule()`：记录 `request_admitted` 或 `request_scheduled`，字段包括 request id、num cached tokens、num computed tokens、本 step new tokens。

L0 验收标准：

- `KVFABRIC_LIFECYCLE=0` 时，prebenchmark 与 vanilla 行为一致。
- `KVFABRIC_LIFECYCLE=1` 时，`medium_prefix_reuse` 能产生 JSONL，且包含 `prefix_lookup`、`block_sealed`、`block_touched`、`cooling_transition`、`block_evicted` 中至少前三类。
- 日志不记录完整 prompt、不记录 tensor，只记录 hash、block id、token 数、状态和时间。
- 增加一个 summary 脚本，把 JSONL 汇总为 prefix hit blocks、sealed blocks、touched blocks、evicted blocks、平均 share degree。

### L1：冷却分层，仍尽量少改变行为

L1 的目标是让 ref count 归零的 block 不再只是“普通 free block”，而是先拥有逻辑状态。第一版可以只改变元数据，不改变 free queue；第二版再在候选选择时使用这些状态。

建议状态规则：

- `ref_cnt > 0`：`SHARED_ACTIVE` 或 active。
- `ref_cnt == 0` 且处于高命中 family、prefix depth 较浅或 branch factor 较高：`COOLING_HOT`。
- `ref_cnt == 0` 且有历史命中但共享价值一般：`COOLING_WARM`。
- `ref_cnt == 0` 且私有尾部、低命中、深层 block：`CANDIDATE`。

L1 第一版不需要真的新建物理池；只在 side table 里写 `logical_pool` 字段。这样报告中已经能展示“共享主干与私有尾部被区分对待”。

L1 验收标准：

- medium prefix reuse 中，共享前缀 block 的 `COOLING_HOT` 比例高于私有尾部。
- cache pressure 类测试中，私有尾部或冷 block 更多进入 `CANDIDATE`。
- 行为改动开关仍可关闭，关闭后完全回到 vanilla。

### L2：family-aware 二阶段驱逐

L2 才开始真正改变 vLLM 的驱逐选择。不要全局扫描所有 block，而是基于当前 free queue 的前 K 个候选做二阶段选择。

当前 vLLM 在 `BlockPool.get_new_blocks(num_blocks)` 中直接：

```text
free_block_queue.popleft_n(num_blocks)
_maybe_evict_cached_block(block)
ref_cnt += 1
```

建议新增策略开关：

```text
KVFABRIC_LIFECYCLE_POLICY=observe | cooling | shared_aware
KVFABRIC_EVICTION_CANDIDATE_MULTIPLIER=4
```

`shared_aware` 模式下流程改为：

1. 从 free queue 前端取 `K = multiplier * num_blocks` 个安全候选，或在不破坏链表的前提下 peek 候选。
2. 过滤掉 null block、状态异常 block。
3. 为候选计算 `RetainScore`。
4. 选择 retain score 最低的 `num_blocks` 作为 victims。
5. 从 free queue 删除 victims；未选中的候选保持原有顺序或按轻量规则放回。
6. 对 victims 调用 `_maybe_evict_cached_block()`，然后分配给新请求。

初始评分可以直接从最小闭环迁移：

```text
RetainScore =
  w_hit * hit_count
  + w_share * share_degree
  + w_prefix * prefix_position_value
  + w_recompute * recompute_cost
  + w_branch * branch_factor
  - w_age * age
```

注意这里是保留价值，驱逐时选最低分。`prefix_position_value` 建议让浅层 block 更高分；`age` 表示长期未访问的块更容易被淘汰。第一版不必追求公式复杂，关键是每次驱逐要能解释“为什么这个 block 被选中”。

L2 验收标准：

- 同一 workload 下可以跑 vanilla、observe、shared_aware 三组。
- JSONL 中每次 eviction 有 candidate rank、retain score、hit count、share degree、prefix depth。
- shared-aware 策略下，共享主干 block 的驱逐比例低于 vanilla 近似 LRU。
- 指标至少包括 `eviction_count`、`shared_anchor_eviction_ratio`、`tail_eviction_ratio`、`regretful_eviction_rate` 或可替代的 rebuild proxy。

### L3：scheduler 协同，作为可选增强

L3 不建议作为第一轮必须交付。它把 KVFabric 从 cache policy 推向 serving policy，风险更高，但展示价值也更大。

可做的最小版本：

- scheduler 只接收 lifecycle hint 并记录，不改变调度；
- 在高 KV pressure 时，记录哪些 request 属于 shared-prefix-heavy，哪些属于 long-tail-heavy；
- 后续再尝试降低低复用请求的 lookahead 或优先接纳高复用 family 请求。

L3 验收标准：

- scheduler 输出中可看到 request class、pressure level、expected reuse；
- 未开启策略时不改变请求顺序；
- 开启策略后只在高压场景生效，并可通过日志解释调度差异。

## 4. 与现有最小闭环的迁移关系

`experiments/benchmarks/lifecycle_policy/` 中已经有 `BlockLife`、`EvictionEvent`、shared-aware 权重和 workload 指标。迁移时不要直接复制整个 benchmark 脚本进 vLLM，而应拆成三部分：

1. 数据结构迁移到 `kvfabric_lifecycle.py`：保留 block meta、evicted shadow、score 计算。
2. 事件语义迁移到 vLLM 打点：`block_sealed`、`block_touched`、`block_evicted` 等事件由真实 vLLM 调用触发。
3. 指标汇总保留在 experiments 脚本侧：读 JSONL，输出 `metrics.json` 与 `summary.md`，再与 prebenchmark 和 benchmark 结果对齐。

这样可以保持 vLLM 热路径轻量，也能让实验逻辑仍然集中在 `experiments/`。

## 5. 三人分工方案

三个人应按“源码观测层 / 策略实现层 / 实验验收层”分工，而不是每个人各改一半同一个文件。这样依赖最少，冲突最少，也能各自独立推进。

### A：生命周期元数据与日志负责人

主要目标：完成 L0，使 vLLM 真实运行时能输出生命周期事件。

负责文件：

- `vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py`
- `vllm_workspace/overlay/vllm/v1/core/block_pool.py`
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py`
- JSONL summary 脚本，可放在 `experiments/prebenchmark_validation/examples/` 或 `experiments/benchmarks/lifecycle_policy/examples/`

具体任务：

1. 设计并实现 `LifecycleBlockMeta`、`PrefixFamilyMeta`、`EvictedShadow`、`LifecycleEventLogger`。
2. 实现环境变量开关，默认关闭。
3. 在 `get_computed_blocks()`、`cache_full_blocks()`、`touch()`、`free_blocks()`、`_maybe_evict_cached_block()` 加最小打点。
4. 保证日志字段稳定，供 B 和 C 使用。
5. 写一个本地 summary：输入 JSONL，输出事件计数、block 状态计数、prefix hit block 统计、eviction 统计。

独立性边界：

- A 不改变驱逐策略，不改 free queue 行为。
- A 给 B 提供 `compute_retain_score(meta)` 所需字段。
- A 给 C 提供日志格式和 summary 输出。

阶段交付：

- 一个最小 PR 或 patch：开启 `KVFABRIC_LIFECYCLE=1` 后能看到真实 vLLM 生命周期事件。
- 一份 JSONL 字段说明。

### B：shared-aware 策略与驱逐负责人

主要目标：完成 L1/L2，让 vLLM 能在可控开关下使用共享感知候选选择。

负责文件：

- `vllm_workspace/overlay/vllm/v1/core/block_pool.py`
- `vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py`
- 必要时少量修改 `kv_cache_utils.py` 中 free queue 辅助方法，但要谨慎。

具体任务：

1. 基于 A 的 side table 实现 `COOLING_HOT / COOLING_WARM / CANDIDATE` 逻辑状态。
2. 从最小闭环迁移 shared-aware score。
3. 为 `BlockPool.get_new_blocks()` 增加策略分支：`observe` 保持原行为，`shared_aware` 启用二阶段候选。
4. 每次驱逐输出 candidate score、rank、选择原因。
5. 维护 `EvictedShadow`，初步支持 rebuild/regret 检测。如果真实 rebuild 难以第一版准确判断，可以先记录相同 hash 再次 sealed 的时间间隔作为 proxy。

独立性边界：

- B 不负责跑完整 benchmark，只提供策略开关和解释性日志。
- B 不改 scheduler，不改 worker，不改 kernel。
- B 使用 A 提供的 meta，不额外发明一套重复状态。

阶段交付：

- `KVFABRIC_LIFECYCLE_POLICY=shared_aware` 可运行。
- shared-aware 与 vanilla 在同一 workload 下的 eviction 事件可对比。
- 若策略导致性能明显下降或异常，可一键切回 observe。

### C：实验、验收和报告负责人

主要目标：把 A/B 的源码改动变成可复现验收结果，防止“代码改了但无法证明有效”。

负责目录：

- `experiments/prebenchmark_validation/`
- `experiments/benchmarks/lifecycle_policy/`
- `experiments/paper_reproductions/vllm_performance_benchmark/`
- `docs/current/` 和阶段报告

具体任务：

1. 固化三类运行脚本：vanilla、observe、shared-aware。
2. 为 prebenchmark 增加 lifecycle JSONL 路径收集和 summary。
3. 设计最小 A/B 矩阵：
   - `medium_prefix_reuse`：功能验证和 prefix hit；
   - `soak_prefix_reuse_20min`：稳定性；
   - cache pressure 或合成高压场景：观察驱逐差异；
   - prefix on/off：确认无共享时不误判收益。
4. 汇总指标：
   - prefix cache hit rate；
   - sealed/touched/evicted block 数；
   - shared anchor eviction ratio；
   - tail eviction ratio；
   - regretful eviction proxy；
   - completion tokens/s、latency p50/p95、KV cache usage；
   - 日志与策略开销。
5. 写阶段报告，解释哪些收益来自真实 vLLM，哪些仍是 synthetic proxy。

独立性边界：

- C 不直接修改核心 vLLM 策略。
- C 通过环境变量和脚本组合 A/B 的代码。
- C 对 A/B 提供回归失败和指标异常反馈。

阶段交付：

- 一套可一键运行的验收脚本。
- 一份 `summary.md`，能回答“策略是否保留了共享主干、是否减少错误驱逐、代价是多少”。

## 6. 合并顺序与协作方式

推荐按以下顺序合并，避免三个人互相阻塞。

1. A 先合并 `kvfabric_lifecycle.py` 空框架、环境变量、JSONL logger，不接入太多打点。
2. A 接入 L0 打点，C 同步写 summary 脚本。
3. C 用 vanilla/observe 跑 prebenchmark，确认行为一致和日志可用。
4. B 基于 A 的 meta 增加 cooling 状态，只记录不改变行为。
5. C 跑 L1 验证，检查共享主干与私有尾部是否能被区分。
6. B 增加 shared-aware 二阶段驱逐策略。
7. C 跑 vanilla vs shared-aware A/B，生成阶段报告。
8. 若 L2 稳定，再讨论 L3 scheduler hint。

每次合并必须满足：

- 默认配置下不开启 KVFabric 行为；
- `KVFABRIC_LIFECYCLE=0` 不产生 JSONL；
- 打点不记录 prompt 明文和 tensor；
- 每次策略行为改动都能通过环境变量关闭；
- 每次实验都保留 config、env、metrics、summary。

## 7. 近期两周可执行计划

第一阶段，1 到 2 天：

- A 建立 `kvfabric_lifecycle.py` 与 logger。
- C 准备 vanilla/observe/shared-aware 的运行环境变量模板。
- B 阅读 `FreeKVCacheBlockQueue`，确认是否需要新增 peek/remove 辅助方法。

第二阶段，3 到 5 天：

- A 完成 L0 打点。
- C 跑 `medium_prefix_reuse` 和 `prefix_reuse_smoke`，验证 JSONL。
- B 根据 JSONL 字段设计 retain score，不改变行为。

第三阶段，3 到 5 天：

- B 完成 cooling 状态和 shared-aware 候选选择。
- C 跑最小 A/B，比较 vanilla、observe、shared-aware。
- A 修正日志字段和 summary 兼容问题。

第四阶段，2 到 3 天：

- 三人共同整理阶段结果。
- 如果 L2 效果稳定，写入报告与 PPT：强调“真实 vLLM 中已接入生命周期观测和共享感知驱逐原型”。
- 如果 L2 效果不稳定，报告中保留 L0/L1 作为稳定成果，把 L2 标注为实验性策略。

## 8. 最终验收标准

最低验收：

- 源码 overlay 中有可关闭的生命周期观测模块。
- vLLM 真实运行时能输出 block/request 级 JSONL。
- prebenchmark 能正常跑完，且日志能汇总。
- 文档能说明每类事件来自哪个 vLLM 函数。

较好验收：

- L1 cooling 状态能区分共享主干和私有尾部。
- shared-aware 策略可运行，且在共享前缀 workload 中减少共享主干驱逐。
- A/B 报告包含行为指标和性能开销。

优秀验收：

- 在高 KV pressure 场景下，shared-aware 策略降低 regretful eviction proxy 或 rebuild proxy。
- prefix hit、saved prefill tokens、KV cache usage、latency/throughput 与 lifecycle 指标能放在同一张结果表中解释。
- scheduler hint 有 observe 版，为后续 L3 留出接口。

## 9. 风险与规避

最大风险不是策略公式不够复杂，而是过早改动 worker/kernel 语义。规避方式是坚持 Python 控制面、side table、开关化和 A/B。

第二个风险是日志过重影响吞吐。规避方式是默认关闭、JSONL 精简、按事件而不是按 token 记录，summary 放到实验后处理。

第三个风险是 shared-aware 在小显存 WSL2 环境中效果不稳定。规避方式是把结论拆开：功能正确性、行为解释性、性能收益分别报告；不要把 synthetic 闭环收益直接宣称为真实 GPU 性能收益。

第四个风险是三人同时改同一文件冲突。规避方式是 A 先提供公共模块和事件接口，B 只接策略分支，C 不碰核心策略文件。

## 10. 下一步最具体的第一刀

第一刀建议不是直接改驱逐，而是新增可关闭的生命周期观测层：

1. 在 overlay 中新增 `vllm/v1/core/kvfabric_lifecycle.py`。
2. 在 `BlockPool.__init__()` 中初始化 lifecycle tracker。
3. 在 `cache_full_blocks()` 记录 `block_sealed`。
4. 在 `touch()` 记录 `block_touched`。
5. 在 `_maybe_evict_cached_block()` 记录 `block_evicted`。
6. 在 `KVCacheManager.get_computed_blocks()` 记录 `prefix_lookup`。
7. 应用 overlay 到 `../vllm-v0.19.0`。
8. 跑 `run_prefix_reuse_smoke.sh` 和 `run_medium_prefix_reuse.sh`。
9. 用 summary 脚本证明日志链路可用。

这一步完成后，项目就从“文档和合成闭环”进入了“真实 vLLM 控制面的生命周期闭环”。之后再做 cooling 和 shared-aware 驱逐，风险会低很多。
