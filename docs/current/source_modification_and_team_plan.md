# KVFabric 当前源码状态与团队收尾方案

本文档面向当前已经落地的 vLLM 控制面原型。它不再描述“下一阶段准备怎么改源码”，而是总结已经完成的源码改造、实验闭环和后续收尾任务。

## 当前状态判断

KVFabric 已经从 baseline 和合成闭环推进到真实 vLLM Python 控制面 prototype。当前实现包括：

- lifecycle side table 与 JSONL 事件流；
- vLLM `BlockPool`、`KVCacheManager` 等路径上的 prefix lookup、block sealed、touch、evict、rebuilt-from-eviction 探针；
- Prometheus 指标探针和 `read_metrics.sh` 汇总；
- `shared_aware` retain-score 策略；
- `family_protect` 共享主干保护策略；
- request-aware / length-aware admission control；
- prebenchmark A/B 运行、lifecycle summary 和 A/B comparison 脚本；
- 长时间对话压测程序，用于构造多轮、长上下文和分叉型请求。

当前项目阶段应表述为：

> 基于 vLLM Python 控制面的 KVCache 生命周期管理原型已初步跑通；正在进行代表性 workload 复跑、结果整理和最终报告收尾。

## 已完成源码改造

### Lifecycle 模块

新增文件：

```text
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
```

主要能力：

- 维护 `LifecycleBlockMeta`；
- 记录 block hash、prefix depth、ref count、hit count、share degree、branch factor、recompute cost；
- 保存 `EvictedShadow`，用于识别驱逐后同 hash 重建；
- 通过环境变量开关启用 JSONL event logger；
- 提供 retain score、protected 判断、family protect 线性选择器和 admission gate。

### BlockPool 接入

文件：

```text
vllm_workspace/overlay/vllm/v1/core/block_pool.py
```

接入点：

- 初始化 `KVFabricLifecycleTracker`；
- `cache_full_blocks()` 记录 `block_sealed`；
- `get_new_blocks()` 根据 `KVFABRIC_EVICTION_POLICY` 选择 LRU、shared-aware 或 family-protect；
- `_maybe_evict_cached_block()` 记录 `block_evicted`；
- `touch()` 记录 prefix cache block 复用；
- `free_blocks()` 记录 ref count 变化；
- `reset_prefix_cache()` 重置 lifecycle tracker。

### KVCacheManager 接入

文件：

```text
vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py
```

接入点：

- `get_computed_blocks()` 记录 `prefix_lookup`；
- 将 request id、prompt tokens、hit tokens、skip prefix cache 等字段写入 lifecycle tracker；
- 与 metrics collector 对齐 prefix cache request hit 和 token hit。

### Metrics 接入

相关文件：

```text
vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py
vllm_workspace/overlay/vllm/v1/metrics/stats.py
vllm_workspace/overlay/vllm/v1/metrics/loggers.py
```

主要能力：

- block lookup queries / hits；
- block allocations / cached / evictions；
- block lifetime、idle before evict、access count；
- rebuild gap、eviction regret；
- metadata update time、block lookup time、waiting time；
- 请求级 TTFT、TPOT、E2E latency 等指标对齐 A/B 报告。

## 当前策略

### LRU

作为 vLLM 原路径对照。`KVFABRIC_LIFECYCLE=1` + `KVFABRIC_EVICTION_POLICY=lru` 时，只记录 lifecycle 事件，不改变驱逐顺序。

### shared-aware

基于 retain score 对候选 block 做排序。它适合解释策略因子，但 Python 排序开销较高，因此不是当前最终推荐策略。

### family-protect

当前最重要的策略。它保持 free queue 原始顺序，遇到 protected block 时延后驱逐，只有普通候选不足时才回退驱逐 protected block。

protected 判断来自：

- hit count；
- share degree；
- branch factor。

这个策略在普通无共享场景中基本不触发，在模板化 prompt、相似多轮、长期 family 回访场景中能减少共享主干误驱逐。

### admission control

用于限制冷长尾请求在低 free ratio 下污染 prefix cache。当前保留为可配置策略项：

```text
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

它的结论应谨慎表述：admission control 有助于减少缓存污染，但阈值仍是经验值，需要结合 workload 解释。

## 已完成阶段节点

### 2026-05-31：探针与封装初步完成

这一天可以作为“从设计进入真实 vLLM 控制面观测”的节点：

- lifecycle tracker 初步成型；
- block/request 级事件能落到 JSONL；
- side table 字段和 summary 脚本具备；
- overlay 可应用到 vLLM 工作树运行；
- 项目从合成闭环推进到真实 vLLM 控制面事件闭环。

### 2026-06-07：长对话压测与策略验证完成

这一天可以作为“策略原型初步验证通过”的节点：

- 长时间对话压测程序完成设计与实现；
- `shared_aware`、`family_protect`、admission control 初步接入；
- 普通无共享、模板 family、cache pressure 等 workload 已经可以 A/B；
- 初步结果显示，普通场景低开销退化，模板/相似多轮场景可减少 rebuilt-from-eviction，提高 prefix-hit tokens。

## 后续收尾分工

### A：源码与 overlay 状态负责人

任务：

- 确认 overlay 文件与 `vllm_workspace/upstream_manifest.txt` 一致；
- 保证 `KVFABRIC_LIFECYCLE=0` 或未设置时不会改变 vLLM 行为；
- 梳理环境变量说明；
- 保留少量代表性 patch/diff，避免最终报告只靠文字。

### B：A/B 复跑负责人

任务：

- 复跑并保存代表性场景：
  - `ordinary_unique_cold.json`
  - `template_family_revisit.json`
  - `template_family_revisit_cycles.json`
- 每个场景至少保留 `config.json`、`metrics.json`、`kvfabric_lifecycle_metrics.json`、`prometheus_metrics_summary.json` 和 `ab_comparison.md`。
- 尽量补三组对照：
  - prefix caching off；
  - prefix caching on + LRU；
  - prefix caching on + `family_protect`。

### C：报告与文档负责人

任务：

- 更新 README、roadmap、overlay README、prebenchmark README；
- 将 `2026-05-31` 和 `2026-06-07` 写入日志；
- 把阶段结论写成“场景化收益”，避免泛化为所有 workload 提速；
- 明确未实现内容：非严格 chunk 级共享、真实 CoW、显式 prefix-family tree、scheduler 改调度。

## 最终表述建议

最终报告中建议采用以下口径：

> KVFabric 已经在 vLLM Python 控制面实现生命周期观测、共享主干保护和可复现 A/B 工具链。在普通无共享请求中，策略可低开销退化；在模板化 prompt、相似多轮和长期共享前缀回访场景中，KVFabric 能减少共享主干误驱逐，降低 rebuilt-from-eviction，并提高 prefix-hit tokens。当前 prototype 的收益主要来自 KVCache 资源管理质量改善，而不是对所有 workload 的通用吞吐加速。
