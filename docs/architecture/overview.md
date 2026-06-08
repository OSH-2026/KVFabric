# Architecture Overview

本文档描述 KVFabric 当前已经落地的架构口径：基于 vLLM Python 控制面的 KVCache 生命周期管理原型。

现阶段的核心是：在保持 vLLM 执行路径和底层 block 语义稳定的前提下，把 KV block 的创建、共享、释放、驱逐和重建变成可观测、可评分、可 A/B 对比的系统对象。

## 项目定位

KVFabric 关注的是 LLM serving 中 KVCache 的资源管理问题。vLLM 已经提供了 PagedAttention、block pool、prefix caching 和 free queue 等基础机制；KVFabric 在这些机制之上增加生命周期封装和共享感知策略，用来回答：

- 哪些 KV block 是长期可复用的共享主干；
- 哪些 KV block 只是低复用私有尾部；
- 显存压力下应该优先保留谁、驱逐谁；
- 如果驱逐后很快重建，如何记录这次策略后悔；
- 策略是否真的改善 prefix-hit tokens、rebuilt-from-eviction、TTFT 或 requests/s。

因此，KVFabric 当前不是替换 vLLM，也不是重写推理执行路径，而是在 vLLM 控制面中实现一层轻量的 lifecycle manager。

## 当前架构

```text
        Workloads / Benchmarks
  ordinary, template family, long dialogue,
  cache pressure, prefix reuse, A/B suites
                  |
                  v
        vLLM OpenAI-Compatible Serving
                  |
                  v
        vLLM Python Control Plane
  Scheduler / KVCacheManager / BlockPool
                  |
                  v
        KVFabric Lifecycle Layer
  side table / events / retain score /
  family protect / admission / metrics
                  |
                  v
        vLLM Worker + Attention Runtime
       unchanged physical block semantics
```

## 核心模块

### 1. Lifecycle Side Table

当前新增模块为：

```text
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
```

它维护 `block_id -> LifecycleBlockMeta`，记录：

- `block_hash`
- `prefix_depth`
- `ref_count`
- `hit_count`
- `share_degree`
- `branch_factor`
- `recompute_cost_tokens`
- `state`
- `retain_score`

这张表是旁路元数据，不替代 vLLM 原本的 `KVCacheBlock`。关键状态仍以 vLLM 的 block id、hash、ref count 和 free queue 为准。

### 2. Event Logger

KVFabric 通过 JSONL 记录事件流。默认关闭，打开后只记录 hash、block id、token 数、状态和指标，不记录 prompt 明文或 KV tensor。

主要事件：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `eviction_candidates_ranked`
- `block_evicted`

这些事件用于后处理 summary、A/B 对比和报告解释。

### 3. Metrics Probe

overlay 扩展了 vLLM metrics/stats 路径，使实验可以从 `/metrics` 读取：

- prefix cache request hit rate；
- prefix token hit rate；
- KV block lookup hit rate；
- evicted blocks；
- eviction regret proxy；
- metadata update overhead；
- TTFT、TPOT、E2E latency 等请求级指标。

JSONL 事件用于解释策略行为，Prometheus 指标用于量化服务表现。

### 4. Shared-Aware Policy

`shared_aware` 策略根据 retain score 对候选 block 排序。retain score 综合考虑：

- 历史命中；
- 共享程度；
- prefix depth；
- recompute cost；
- branch factor。

驱逐时选择保留价值最低的候选 block。

### 5. Family-Protect Policy

`family_protect` 是当前更稳定的策略。它不在普通场景中强行排序，而是保持 vLLM free queue 的原始 LRU 顺序，只在候选窗口中遇到 protected block 时延后驱逐。

protected block 的判定依据包括：

- `hit_count >= KVFABRIC_PROTECT_MIN_HIT_COUNT`
- `share_degree >= KVFABRIC_PROTECT_MIN_SHARE_DEGREE`
- `branch_factor >= KVFABRIC_PROTECT_MIN_BRANCH_FACTOR`

这个策略更适合当前 Python-layer prototype，因为它能保护共享主干，同时降低热路径排序开销。

### 6. Admission Control

KVFabric 还加入了 request-aware / length-aware admission control。它的作用不是直接提高 prefix hit，而是在低 free ratio 时减少冷长尾请求对 prefix cache 的污染。

典型参数：

```text
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

当前 admission control 仍属于经验性策略，报告中应作为可配置优化项解释，而不是项目唯一核心贡献。

## vLLM 改造边界

当前 overlay 主要触及：

- `vllm/v1/core/block_pool.py`
- `vllm/v1/core/kv_cache_manager.py`
- `vllm/v1/core/kv_cache_utils.py`
- `vllm/v1/core/kv_cache_metrics.py`
- `vllm/v1/metrics/stats.py`
- `vllm/v1/metrics/loggers.py`
- `vllm/v1/core/sched/*`

保持不变的边界：

- 不改变 worker 已下发的 block table 语义；
- 不做物理 KV block 去重；
- 不实现真实写时复制；
- 不实现任意 chunk 级非严格前缀共享；
- 不修改 attention kernel 的读写路径。

这个边界保证当前原型可以通过环境变量关闭或回退，便于做 A/B 和复跑。

## 当前实验解释

KVFabric 的结果应按 workload 分类解释：

- 普通无共享请求：策略通常不触发 family protection，性能差异应接近测量噪声。
- 模板化 prompt：共享前缀具有长期复用价值，KVFabric 能保护共享主干。
- 相似多轮对话：历史上下文形成重复 family，策略可减少 LRU 误驱逐。
- cache pressure：能观察 eviction quality，但端到端吞吐收益取决于 LRU 是否真的误杀热点 block。
- 长时间对话压测：用于构造更接近真实服务的长上下文和多轮分叉场景。

最终报告应强调“KVCache 资源管理质量和可解释性”，避免把当前 Python prototype 描述为通用高吞吐加速器。
