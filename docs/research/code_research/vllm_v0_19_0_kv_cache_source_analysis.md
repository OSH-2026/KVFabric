# vLLM v0.19.0 KVCache 源码分析报告

## 0. 分析对象与结论摘要

本报告分析的源码位于项目目录之外：

- 源码路径：`/home/qy-dream/OSH_Project/vllm-v0.19.0`
- 克隆版本：`v0.19.0`
- 当前提交：`2a69949bdadf0e8942b7a1619b229cb475beef20`
- 参考文档：`/home/qy-dream/OSH_Project/KVFabric/docs/reports/feasibility_report.md`

本报告重点阅读 vLLM v1 中与 KVCache 分配、前缀复用、block 回收、worker 侧 block table 和 attention 读写相关的源码。结论如下：

1. vLLM v0.19.0 已经具备较完整的 block 化 KVCache 管理基础。`KVCacheBlock` 保存 `block_id`、`ref_cnt`、`block_hash` 与 free-list 指针；`BlockPool` 维护全局 block 池、prefix-cache 哈希表和按驱逐顺序排列的 free queue。
2. 当前 Automatic Prefix Caching 是严格的 full-block 前缀匹配。block hash 是链式哈希，包含父 block hash、当前 block token 以及 LoRA、多模态、cache salt、prompt embeds 等额外 key。因此它能复用“从开头开始完全相同”的 full block 前缀，但无法复用非前缀的局部重叠，也无法复用未填满尾块。
3. vLLM 当前不做物理 block 去重。即使两个 block hash 相同，系统也不会改写已经分配出去的 block ID，因为 worker 侧 block table 依赖 append-only 的 block ID 序列。这构成后续原型设计的重要正确性边界。
4. 从工程风险看，初始切入点宜放在 Python 层的 `KVCacheManager`、`SingleTypeKVCacheManager` 和 `BlockPool`，而不是 attention kernel。可以先通过 side table 增加生命周期统计，再在 free queue 前端候选中做二阶段驱逐评分。
5. 对“共享后分叉”需要区分两类情况：如果多个请求共享的是从序列开头开始的若干完整 block，vLLM 当前已经可以复用这些 block；但它不会显式维护分叉树，也不会在一个 miss 后继续寻找后续 chunk 级重叠。因此 L1 目标更适合定义为“记录共享链、分叉链，并将其用于驱逐价值评估”，而不是直接重写物理共享机制。

---

## 1. 与可行性报告的对应关系

可行性报告提出的核心路线是“调研分析 -> 生命周期建模 -> 原型设计 -> 实验验证”，并强调先做最小可行原型。结合源码结构，这一路线可以对应到以下对象：

| 可行性报告中的需求 | vLLM 源码支撑点 | 结论 |
| --- | --- | --- |
| block 生命周期建模 | `vllm/v1/core/kv_cache_utils.py:109` 的 `KVCacheBlock` | 已有 `block_id`、`ref_cnt`、`block_hash`，但缺少 hit_count、branch_factor、recompute_cost 等长期价值字段 |
| 前缀复用分析 | `KVCacheManager.get_computed_blocks()`、`FullAttentionManager.find_longest_cache_hit()` | 已支持严格 full-block 前缀命中，命中后增加 ref count |
| 驱逐策略分析 | `BlockPool.get_new_blocks()`、`BlockPool._maybe_evict_cached_block()`、`FreeKVCacheBlockQueue` | 当前以 free queue 顺序驱逐，近似 LRU + 尾块优先 |
| 低侵入原型 | `BlockPool` 与 `KVCacheMetricsCollector` | 可以先在 Python 层统计和调整候选顺序，暂不触碰 CUDA/Triton kernel |
| 实验指标采集 | `PrefixCacheStats`、`SchedulerStats`、`KVCacheMetricsCollector` | 已有 prefix hit、KV usage、eviction lifetime/idle/reuse gaps 等基础指标 |
| 共享后分叉 | 链式 block hash + request block table | 能表达严格前缀共享后的尾部分叉，但没有显式分叉树和跨 chunk 复用 |

据此，原型工作可按“观测层 -> 策略层 -> 增强共享层”推进，与可行性报告第 8.4 节的最小原型策略一致。

---

## 2. 总体执行链路

vLLM v1 的 KVCache 管理可以分为控制面和执行面两部分。

控制面主要在 scheduler 进程内完成：

```text
Request
  -> Request.update_block_hashes()
  -> Scheduler.schedule()
  -> KVCacheManager.get_computed_blocks()
  -> KVCacheCoordinator.find_longest_cache_hit()
  -> SingleTypeKVCacheManager.find_longest_cache_hit()
  -> BlockPool.get_cached_block()
  -> KVCacheManager.allocate_slots()
  -> SingleTypeKVCacheManager.allocate_new_computed_blocks()
  -> BlockPool.touch()
  -> SingleTypeKVCacheManager.allocate_new_blocks()
  -> BlockPool.get_new_blocks()
  -> BlockPool.cache_full_blocks()
  -> SchedulerOutput(block_ids, num_computed_tokens, new_block_ids_to_zero)
```

执行面主要在 worker/model runner 内完成：

```text
SchedulerOutput
  -> GPUModelRunner.add_requests()/update_requests()
  -> BlockTables.append_block_ids()
  -> BlockTables.compute_slot_mappings()
  -> model forward context
  -> Attention backend metadata
  -> do_kv_cache_update(key, value, kv_cache, slot_mapping)
  -> attention forward reads kv_cache by block_table
```

这条链路表明：scheduler 负责决定“请求使用哪些 block ID”；worker 根据 block table 生成 slot mapping，把逻辑 token 位置映射到物理 KV cache 页。在不改变 block ID 语义和 block table append-only 约束的前提下，可以优先在 Python 层进行生命周期统计和驱逐策略实验。

---

## 3. 关键源码文件地图

| 文件 | 作用 | 与本项目的关系 |
| --- | --- | --- |
| `vllm/v1/request.py` | Request 状态、token 序列、block hashes | 前缀哈希从这里随 request 创建和 token 追加而更新 |
| `vllm/v1/core/kv_cache_utils.py` | `KVCacheBlock`、free queue、block hash 计算 | 生命周期对象和 full-block 哈希边界 |
| `vllm/v1/core/block_pool.py` | 全局 block 池、prefix-cache hash map、free queue、eviction | 驱逐策略与生命周期元数据的主要切入点 |
| `vllm/v1/core/kv_cache_manager.py` | scheduler 侧 KVCache 总入口 | `get_computed_blocks()`、`allocate_slots()` 是核心控制面 API |
| `vllm/v1/core/kv_cache_coordinator.py` | 多 KV cache group 协调 | 处理 full/sliding/local/Mamba 等不同 group |
| `vllm/v1/core/single_type_kv_cache_manager.py` | 单一 KV cache 类型的块管理 | 负责 per-request block list、touch、allocate、free、cache |
| `vllm/v1/core/sched/scheduler.py` | 请求调度主循环 | prefix hit 如何影响 `num_computed_tokens` 和调度 |
| `vllm/v1/core/sched/output.py` | scheduler 到 worker 的数据结构 | block IDs、computed tokens、new blocks to zero 的传递格式 |
| `vllm/v1/worker/gpu_worker.py` | GPU worker 选择 V1/V2 model runner | 说明 v0.19.0 同时存在两个 GPU runner 路径 |
| `vllm/v1/worker/gpu/model_runner.py` | V2 GPU runner | 读取 scheduler output，维护 `BlockTables`，生成 slot mapping |
| `vllm/v1/worker/gpu/block_table.py` | V2 block table 与 slot mapping kernel | worker 侧正确性边界，不能随意改 block ID |
| `vllm/v1/worker/gpu_model_runner.py` | V1 GPU runner | 旧路径，同样会生成 slot mapping 并传入 attention |
| `vllm/v1/worker/block_table.py` | V1 block table | V1 的 row append 与 slot mapping 逻辑 |
| `vllm/v1/attention/backends/flash_attn.py` | FlashAttention metadata、forward、KV cache update | attention 如何读写 paged KV cache |
| `vllm/v1/attention/ops/triton_reshape_and_cache_flash.py` | Triton 写 KV cache kernel | slot mapping 决定 key/value 写入哪个物理 slot |
| `vllm/v1/kv_cache_interface.py` | KVCache spec 和 group 配置 | block size、page size、不同注意力类型的显存需求 |
| `vllm/v1/core/kv_cache_metrics.py` | block residency metrics | 可扩展生命周期观测指标 |
| `vllm/v1/metrics/stats.py` | `PrefixCacheStats`、`SchedulerStats` | prefix hit、KV usage、eviction events 的统计载体 |

---

## 4. 核心数据结构

### 4.1 `KVCacheBlock`

`vllm/v1/core/kv_cache_utils.py:109` 定义了 `KVCacheBlock`：

- `block_id`：物理 KV block 编号。
- `ref_cnt`：当前引用该 block 的请求数量。
- `_block_hash`：full block 被缓存后才拥有的 hash key，包含 block hash 和 KV cache group id。
- `prev_free_block` / `next_free_block`：free queue 的双向链表指针。
- `is_null`：null block 标记，用于 sliding window、Mamba align 等特殊场景。

该类字段较少，只保存必要的分配与 prefix cache 元数据。因此，初始阶段不宜直接把所有生命周期字段加入 `KVCacheBlock`，更适合使用 side table：

```text
block_id -> LifecycleMeta(
  last_access_ts,
  hit_count,
  share_degree,
  prefix_depth,
  branch_factor,
  recompute_cost,
  last_evicted_hash,
)
```

这种方式可以减少对核心对象的改动，也便于在关闭实验开关后退回原始行为。

### 4.2 `BlockHash` 与链式前缀哈希

`vllm/v1/core/kv_cache_utils.py:33` 定义 `BlockHash`，`hash_block_tokens()` 在 `vllm/v1/core/kv_cache_utils.py:535` 计算单个 full block 的哈希。它的输入包括：

- parent block hash；
- 当前 block 的 token ids；
- extra keys，例如 LoRA、多模态输入、cache salt、prompt embeddings。

`get_request_block_hasher()` 在 `vllm/v1/core/kv_cache_utils.py:565` 中只为完整 block 生成 hash。源码明确在尾部不足一个 block 时停止，因此 prefix cache 的自然粒度就是 full block。

链式哈希带来两个重要性质：

1. 它保证命中的是同一条前缀链，不只是某个局部 block 内容相同。
2. 一旦某个 block miss，后续 block 即使 token 内容相同，也因为 parent hash 不同而不会命中。

由此可以看出当前 vLLM 对“共享后分叉”的支持边界：严格前缀共享可以命中；分叉后的再汇合 chunk 不会命中。

### 4.3 `FreeKVCacheBlockQueue`

`FreeKVCacheBlockQueue` 在 `vllm/v1/core/kv_cache_utils.py:158` 定义，使用 `KVCacheBlock` 内部的双向链表指针维护 free blocks。它不使用 Python `deque`，原因是需要 O(1) 删除中间节点。

队列的语义是“前端最先被拿来分配，也就最先被驱逐”。初始时按 block id 排列。请求释放时，`SingleTypeKVCacheManager.free()` 会反向释放请求 block，使尾部 block 排在更靠前的位置。源码注释把这个策略概括为：

- LRU 更靠前；
- 同一请求的一组 block 中，越靠后的 block 更靠前，因为尾块的 hash 链更长，通常更适合先淘汰。

该队列可作为二阶段驱逐的实现位置。由于它已经支持 `remove(block)`，因此可以从队列前 K 个候选中按 `KeepScore` 选择若干低价值 block，而不需要全局排序。

---

## 5. Prefix Cache 的命中与分配流程

### 5.1 Request 创建与 block hash 更新

`Request` 在 `vllm/v1/request.py:58` 定义。它保存 prompt tokens、output tokens、`num_computed_tokens`、`num_cached_tokens`、`block_hashes` 等状态。

关键点：

- `Request.__init__()` 接收 `block_hasher`，然后调用 `update_block_hashes()`。
- `append_output_token_ids()` 追加生成 token 后也会调用 `update_block_hashes()`。
- `update_block_hashes()` 将新生成的 full block hashes 追加到 `request.block_hashes`。
- `skip_reading_prefix_cache` 来自 sampling/pooling params，可让某些请求跳过 prefix cache read。

因此，prefix cache 查询并不是现场重新遍历 token 计算全部 hash，而是复用 `Request` 中已经逐步维护的 `block_hashes`。

### 5.2 Scheduler 查询本地 prefix hit

`Scheduler.schedule()` 是调度主循环。对 waiting 请求，`vllm/v1/core/sched/scheduler.py:609` 开始获取已经缓存的 token：

- 当 `request.num_computed_tokens == 0` 时，调用 `self.kv_cache_manager.get_computed_blocks(request)`。
- 若使用 KVConnector，还会继续查询外部/远程 KV。
- 之后用本地命中 token 数和远程命中 token 数共同决定本 step 还需要计算多少 token。
- 对新请求，`request.num_cached_tokens` 最终被设置为本次命中的 computed tokens。

对 running 请求，scheduler 不会重新做 prefix hit 查找，而是直接根据已有 `num_computed_tokens` 继续追加分配。

### 5.3 `KVCacheManager.get_computed_blocks()`

`vllm/v1/core/kv_cache_manager.py:176` 是 prefix cache 的控制面入口。

主要逻辑：

1. 如果 prefix caching 关闭或请求标记为 skip read，直接返回空命中。
2. 为了获得 logits，即使所有 prompt tokens 都命中，也必须重算最后一个 token，因此最大命中长度是 `request.num_tokens - 1`。
3. 命中长度必须按 block size 对齐，所以有时会重算整个最后 block，而不是只重算一个 token。
4. 实际最长命中由 coordinator 的 `find_longest_cache_hit()` 完成。
5. 如果开启 stats，记录 `PrefixCacheStats`。

这表明当前 prefix cache 的目标是在保证采样正确性的前提下尽量跳过 prefill，因此仍保留最后 token 的重新计算语义。

### 5.4 Coordinator 与不同 KV cache group

`vllm/v1/core/kv_cache_coordinator.py` 根据模型的 KV cache group 选择不同 coordinator：

- `KVCacheCoordinatorNoPrefixCache`：prefix cache 关闭时使用。
- `UnitaryKVCacheCoordinator`：单个 KV cache group。
- `HybridKVCacheCoordinator`：多个 KV cache group，例如 full attention、sliding window、local attention、Mamba 混合。

在初始实验范围内，建议优先选择 decoder-only、单机单 GPU、full attention 路径，此时 `UnitaryKVCacheCoordinator + FullAttentionManager` 是主要路径。Hybrid 路径涉及不同 block size 的 LCM 对齐、sliding/local window 跳块和 Mamba 特殊状态，适合作为后续边界分析。

### 5.5 `FullAttentionManager.find_longest_cache_hit()`

`vllm/v1/core/single_type_kv_cache_manager.py:419` 是 full attention prefix hit 的核心。

它从 `request.block_hashes` 左到右扫描：

```text
for block_hash in block_hashes:
  if block_pool.get_cached_block(block_hash, group_ids):
      append cached block
  else:
      break
```

该逻辑反映出以下特征：

- 命中必须从第一个 block 开始连续发生。
- 遇到第一个 miss 后立即停止。
- `use_eagle` 时会丢掉最后一个 matched block。
- 命中结果按 `alignment_tokens` 对齐。

因此，vLLM 的 prefix cache 是严格最长公共前缀，不是任意子串/子序列缓存。

### 5.6 `KVCacheManager.allocate_slots()`

`vllm/v1/core/kv_cache_manager.py:257` 是分配 slot 的核心 API。它把一次调度中的 token 区间分为：

- `comp`：请求已计算的 tokens；
- `new_comp`：本次新命中的本地 prefix cache tokens；
- `ext_comp`：远程 KVConnector 命中的 tokens；
- `new`：本次需要实际计算的新 tokens；
- `lookahead`：spec decode 预留 tokens。

分配流程是：

1. 先调用 `remove_skipped_blocks()` 回收 sliding/local attention 中窗口外不再需要的 block。
2. 计算需要分配的新 block 数，如果 free blocks 不够，返回 `None`，由 scheduler 尝试 preempt 其他请求。
3. 如果存在本地 prefix hit，调用 `allocate_new_computed_blocks()` 把命中的 block 接到当前 request 的 block list，并通过 `BlockPool.touch()` 增加引用计数。
4. 调用 `allocate_new_blocks()` 从 `BlockPool.get_new_blocks()` 分配新 block。
5. 若 prefix caching 开启且不是延迟缓存场景，调用 `cache_blocks()` 将已经完整的 block 写入 prefix cache hash map。

这表明“命中”和“分配”不是两个完全独立阶段。命中 block 如果本来在 free queue 中，`touch()` 会把它移出 free queue，从而减少可用 free block 数。源码在 `SingleTypeKVCacheManager.get_num_blocks_to_allocate()` 中专门把这类 evictable hit 也算入容量检查。

---

## 6. BlockPool 的缓存、分配与驱逐

### 6.1 `BlockHashToBlockMap`

`vllm/v1/core/block_pool.py:33` 定义了 prefix cache hash map。它支持一个 block hash 对应一个或多个 `KVCacheBlock`。

源码注释明确指出：当前不会去重缓存中的相同 block，因为必须保证已分配的 block ID 不改变，使 block table 保持 append-only。

其结果是：

- vLLM 允许相同 hash 对应多个物理 block。
- prefix hit 时 `get_one_block()` 只返回其中任意一个。
- 不能简单把新完成的重复 block 替换成旧 block，否则 worker 已经拿到的 block table 会失效。

对本项目而言，这一限制基本排除了初始阶段进行物理级去重或迁移的方案。更可控的做法是在元数据层记录重复 hash、共享度和价值，用于后续驱逐决策，而不是改写已经分配出去的 block ID。

### 6.2 `BlockPool.cache_full_blocks()`

`vllm/v1/core/block_pool.py:210` 将请求中已经完整的 block 放入 prefix cache：

- 根据 request 已维护的 `block_hashes` 取 hash。
- 如果 block size 与 hash block size 不同，会用 `BlockHashListWithBlockSize` 重算 group 粒度。
- null block 会跳过，不进入 prefix cache。
- `blk.block_hash` 只允许从 `None` 设置一次，evict 后才可 reset。
- 插入 `cached_block_hash_to_block`。
- 如果开启 KV events，发送 `BlockStored`。

cache 的动作发生在 scheduler 分配之后，不是 worker forward 之后单独确认。也就是说，vLLM 的设计假设本次调度的 full blocks 会在执行中被正常写入对应 KV cache slot。

### 6.3 `BlockPool.get_new_blocks()`

`vllm/v1/core/block_pool.py:320` 是真正从 free queue 拿 block 的地方。

流程：

1. 检查 free block 数是否足够。
2. 从 `free_block_queue.popleft_n(num_blocks)` 拿队首 block。
3. 如果 prefix caching 开启，对每个 block 调用 `_maybe_evict_cached_block()`。
4. 确认 `ref_cnt == 0`，然后 `ref_cnt += 1`。
5. 如果有 metrics collector，记录 allocation。

注意：`get_new_blocks()` 不检查这个 block 是否能 prefix hit。prefix hit 已经在 `get_computed_blocks()` 和 `touch()` 阶段处理；这里拿到的 free block 如果仍在 prefix cache hash map 中，就会被当作 eviction candidate 清掉 hash。

### 6.4 `_maybe_evict_cached_block()`

`vllm/v1/core/block_pool.py:352` 是驱逐动作本身。

该函数职责较集中：

- 调用 metrics collector 的 `on_block_evicted()`；
- 如果 block 没有 hash，说明不是 prefix cache block，直接返回；
- 从 `cached_block_hash_to_block` 删除该 block；
- 调用 `block.reset_hash()`；
- 如果开启 KV events，发送 `BlockRemoved`。

这段逻辑不释放物理 block，因为调用它时 block 已经来自 free queue，`ref_cnt == 0`。它只是在“重新分配这个 free block 前”清掉 prefix cache 身份。

### 6.5 `touch()` 与 `free_blocks()`

`BlockPool.touch()` 在 `vllm/v1/core/block_pool.py:392`：

- prefix hit 时调用。
- 如果 block `ref_cnt == 0`，说明它在 free queue 中但还保留 prefix cache hash，可被 eviction。此时先从 free queue 中 remove。
- 然后 `ref_cnt += 1`。
- metrics collector 记录 access。

`BlockPool.free_blocks()` 在 `vllm/v1/core/block_pool.py:409`：

- 对传入 block 的 `ref_cnt -= 1`。
- 把 `ref_cnt == 0` 且不是 null block 的块追加回 free queue。

`SingleTypeKVCacheManager.free()` 在 `vllm/v1/core/single_type_kv_cache_manager.py:276` 反向释放请求 block，因此尾块会先进入 free queue。`tests/v1/core/test_prefix_caching.py:275` 的断言也验证了释放后的 free queue 顺序。

### 6.6 `evict_blocks()` 与 `reset_prefix_cache()`

`BlockPool.evict_blocks()` 在 `vllm/v1/core/block_pool.py:425`，它按 block ID 从 prefix cache hash table 中驱逐 block。即使 block `ref_cnt > 0`，也只是移除 prefix cache 身份，不会释放正在运行请求持有的物理 block。

`reset_prefix_cache()` 要求除了 null block 外没有其他 used block。否则返回 `False`。这也是正确性边界：不能在运行请求还持有 block 时全局清空 prefix cache 状态，除非先 preempt running requests。

---

## 7. Worker 侧 block table 与 attention 读写路径

### 7.1 SchedulerOutput 传递 block IDs

`vllm/v1/core/sched/output.py` 定义 scheduler 到 worker 的数据结构：

- `NewRequestData.block_ids`：新请求完整 block IDs。
- `NewRequestData.num_computed_tokens`：新请求已经由 prefix cache 或外部 KV 覆盖的 token 数。
- `CachedRequestData.new_block_ids`：已存在请求本 step 追加的新 block IDs。
- `SchedulerOutput.num_common_prefix_blocks`：所有 running requests 的公共前缀 block 数，用于 cascade attention。
- `SchedulerOutput.new_block_ids_to_zero`：Mamba 等需要清零的新增 block ID。

worker 不重新决定 block 分配，只消费 scheduler 给出的 block ID。

### 7.2 v0.19.0 同时存在 V1 与 V2 GPU runner

`vllm/v1/worker/gpu_worker.py:295` 根据 `VLLM_USE_V2_MODEL_RUNNER` 选择：

- V2：`vllm/v1/worker/gpu/model_runner.py`
- V1：`vllm/v1/worker/gpu_model_runner.py`

两条路径在实现细节上不同，但共同点是：它们都维护 request 到 block table 的映射，并生成 attention 所需的 slot mapping。因此，控制面 `KVCacheManager` 和 `BlockPool` 的分析对两条 runner 路径都成立。

### 7.3 V2 `BlockTables`

`vllm/v1/worker/gpu/model_runner.py:608` 处理新请求，把 `NewRequestData.block_ids` 写入 `BlockTables.append_block_ids()`。`update_requests()` 在 `vllm/v1/worker/gpu/model_runner.py:653` 为已有请求追加新 block。

`vllm/v1/worker/gpu/block_table.py:13` 定义 V2 `BlockTables`：

- `append_block_ids()` 把每个 KV cache group 的 block IDs 写入 block table。
- `gather_block_tables()` 根据 batch request index 取本次 forward 需要的 block table。
- `compute_slot_mappings()` 用 Triton kernel 把 token position 映射成 KV cache slot。

slot mapping 的核心公式在 `vllm/v1/worker/gpu/block_table.py:256`：

```text
block_index = position // (block_size * cp_size)
block_offset = position % (block_size * cp_size)
block_number = block_table[request, block_index]
slot_id = block_number * block_size + local_offset
```

无 context parallelism 时就是 `slot_id = block_number * block_size + block_offset`。

### 7.4 Attention 写入 KV cache

FlashAttention backend 在 `vllm/v1/attention/backends/flash_attn.py:795` 实现 `do_kv_cache_update()`：

- 从 `kv_cache` 拆出 key_cache 和 value_cache；
- 调用 `reshape_and_cache_flash(key, value, key_cache, value_cache, slot_mapping, ...)`；
- slot mapping 的长度决定实际写入 token 数。

Triton kernel `reshape_and_cache_kernel_flash()` 在 `vllm/v1/attention/ops/triton_reshape_and_cache_flash.py:37` 读取 `slot_mapping[token_idx]`，再计算：

```text
block_idx = slot_idx // block_size
block_offset = slot_idx % block_size
```

然后把 key/value 写入对应物理 block 和 block offset。

### 7.5 Attention 读取 KV cache

FlashAttention forward 在 `vllm/v1/attention/backends/flash_attn.py:629`：

- 使用 `attn_metadata.block_table` 访问历史 KV；
- 使用 `attn_metadata.seq_lens`、`query_start_loc` 和 `slot_mapping` 组织当前 batch；
- 非 cascade 路径直接调用 `flash_attn_varlen_func()`，传入 `block_table`；
- cascade 路径使用 `common_prefix_len` 把公共前缀和 suffix 分开处理。

因此，block table 是 attention 正确读取历史 KV 的关键接口。如果后续涉及物理迁移、压缩或更复杂的跨请求共享，就必须同步更新 worker block table，并保证 attention metadata 一致。初始原型应尽量避免改动这一部分。

---

## 8. 统计与事件系统

### 8.1 Prefix cache stats

`vllm/v1/metrics/stats.py:115` 定义 `PrefixCacheStats`：

- `requests`：新请求数；
- `queries`：查询 token 数；
- `hits`：命中 token 数；
- `preempted_requests` / `preempted_queries` / `preempted_hits`：被 preempt 后重新调度请求的统计。

`KVCacheManager.get_computed_blocks()` 在 prefix hit 查询后记录 stats。`Scheduler.make_stats()` 在 `vllm/v1/core/sched/scheduler.py:1931` 汇总 `kv_cache_usage`、`prefix_cache_stats`、`kv_cache_eviction_events`。

这些字段可以支持实验中的 prefix token hit rate 和 preempt 后重算分析。

### 8.2 KVCacheMetricsCollector

`vllm/v1/core/kv_cache_metrics.py` 已经有 block residency 的采样式统计：

- `on_block_allocated()`：按采样率记录 block birth time。
- `on_block_accessed()`：记录 last access 与最近最多 4 次 access history。
- `on_block_evicted()`：输出 lifetime、idle time、reuse gaps。

该模块当前主要用于观测，不影响策略本身。后续可以在其旁边扩展面向决策的生命周期 side table，或者将其事件作为 KeepScore 特征来源。

### 8.3 KV events

`BlockPool.cache_full_blocks()` 可发送 `BlockStored`，`_maybe_evict_cached_block()` 可发送 `BlockRemoved`，`reset_prefix_cache()` 可发送 `AllBlocksCleared`。这些事件主要服务分布式或外部系统观测，对初始单机实验不是必要条件，但可以作为后续可视化或 debug 工具。

---

## 9. 面向原型设计的源码映射

### 9.1 生命周期元数据如何映射到现有源码

| 元数据 | 来源 | 更新时机 |
| --- | --- | --- |
| `block_id` | `KVCacheBlock.block_id` | block 创建后固定 |
| `ref_cnt` | `KVCacheBlock.ref_cnt` | `touch()`、`free_blocks()`、`get_new_blocks()` |
| `block_hash` | `KVCacheBlock.block_hash` | `cache_full_blocks()` 设置，`_maybe_evict_cached_block()` 清除 |
| `last_access_ts` | side table | `touch()`、`cache_full_blocks()`、`get_new_blocks()` |
| `hit_count` | side table | prefix hit 后的 `touch()` |
| `share_degree` | `ref_cnt` 或 side table | `touch()` 和 `free_blocks()` |
| `prefix_depth` | request block index | `cache_full_blocks()` 时根据 block index 写入 |
| `recompute_cost` | block index、block_size、模型层数近似 | block cache 完成时估算 |
| `branch_factor` | block hash 链的后继统计 | `cache_full_blocks()` 看到同一 parent 下不同 child 时更新 |
| `eviction_regret` | evicted hash 后续是否重建 | `_maybe_evict_cached_block()` 记录，`cache_full_blocks()` 对比 |

需要注意的是，`BlockHash` 自身只是 bytes，不能反推出 parent hash。如果需要维护分叉关系，应在 `cache_full_blocks()` 中利用 `request.block_hashes` 的顺序显式记录 `parent_hash -> child_hash`。

### 9.2 KeepScore 与二阶段驱逐切入点

可行性报告提出：

```text
KeepScore(b) =
  w1 * Heat(b)
  + w2 * Share(b)
  + w3 * Reuse(b)
  + w4 * PrefixPos(b)
  + w5 * Recompute(b)
```

源码中的较合适落点是 `BlockPool.get_new_blocks()`。当前它直接从 free queue 前端拿 `num_blocks` 个 block。可以调整为：

1. 从 free queue 前端观察 K 个候选，例如 `K = max(num_blocks * alpha, num_blocks)`。
2. 对候选中 `ref_cnt == 0` 的 block 计算 KeepScore。
3. 选择 KeepScore 最低的 `num_blocks` 个作为实际分配或驱逐对象。
4. 用 `FreeKVCacheBlockQueue.remove(block)` O(1) 移除被选 block。
5. 保持默认路径可通过配置关闭，回退到 `popleft_n()`。

该方式的优点是：

- 不改变 worker block table；
- 不改 attention kernel；
- 不影响已被 running request 引用的 block；
- 只在真正要分配 free block 时触发评分；
- 可用当前 free queue 作为 LRU 粗筛，避免全局排序。

### 9.3 初始阶段暂缓内容

以下改动风险较高，建议暂缓到后续阶段：

1. 暂不直接合并两个相同 hash 的物理 block。源码明确不去重是为了保证 block table append-only。
2. 暂不在 block 已经发给 worker 后修改其 block ID。worker slot mapping 和 attention metadata 都依赖该 ID。
3. 暂不缓存未满尾块。`get_request_block_hasher()` 只 hash full blocks，尾块还会继续写入，不具备稳定共享语义。
4. 暂不支持任意 chunk 级重叠。链式哈希和 `find_longest_cache_hit()` 的 break-on-miss 语义决定了这不是小改动。
5. 暂不同时覆盖 hybrid attention、Mamba、KVConnector、DCP/PCP。它们都有额外状态和对齐约束，初始阶段宜先建立单 GPU full attention 基线。

---

## 10. 实现路线参考

### 阶段 A：只观测，不改变策略

目标：得到可解释的 block 生命周期数据。

可关注的改动点包括：

- 在 `BlockPool.cache_full_blocks()` 记录 block hash、prefix depth、parent-child。
- 在 `BlockPool.touch()` 记录 prefix hit、hit count、last access、share degree。
- 在 `BlockPool._maybe_evict_cached_block()` 记录 evicted block hash、idle time、prefix depth、后续是否被重建。
- 在 `Scheduler.make_stats()` 或自定义日志里输出新增统计。

可得到指标：

- block 级 prefix hit rate；
- block lifetime；
- eviction regret；
- 热点 prefix 的保留时间；
- 共享 block 与独占 block 的驱逐差异。

### 阶段 B：生命周期感知驱逐

目标：在不改变 prefix matching 的情况下，改善“哪些 free cached blocks 先被复用/驱逐”。

可关注的改动点包括：

- 在 `BlockPool.get_new_blocks()` 中加入二阶段候选选择。
- 候选仍来自 free queue 前端，保留 LRU 粗筛。
- KeepScore 只对候选计算，避免每 step 全局排序。
- 增加配置项，例如 `enable_lifecycle_eviction`、`lifecycle_candidate_multiplier`、各权重 `w1...w5`。

评估重点：

- 与原始 vLLM 对比 prefix hit 持久性；
- eviction regret 是否下降；
- TTFT p95 是否更稳定；
- Python 调度开销是否可接受。

### 阶段 C：显式分叉关系建模

目标：不一定改变命中语义，先让驱逐策略知道“哪些 block 是共享链的关键节点”。

可采用的做法包括：

- 用 `request.block_hashes` 顺序记录 `parent_hash -> child_hash`。
- 对同一 parent 下的不同 child 计数，得到 `branch_factor`。
- 对被多个请求共享的 parent block 提高 KeepScore。
- 对较深的独占尾链降低 KeepScore。

这一步可以覆盖可行性报告中“共享后分叉”的一部分核心价值：不直接支持任意分叉后的再共享，而是先记录哪些前缀节点支撑了多个后续分支，从而为驱逐决策提供依据。

### 阶段 D：扩展共享增强

只有在 A/B/C 稳定后，再考虑：

- 局部 chunk 级重叠；
- 非严格前缀匹配；
- block 级 copy-on-write；
- worker block table 同步更新；
- attention kernel 或 metadata 适配。

这些属于后续研究方向，不应作为本阶段形成基本闭环的前置条件。

---

## 11. 实验设计与源码指标对应

| 实验负载 | 源码关注点 | 关键指标 |
| --- | --- | --- |
| 完全共享系统提示 | `get_computed_blocks()`、`touch()` | prefix token hit rate、TTFT |
| 单点分叉 | `cache_full_blocks()` 的 parent-child 记录 | shared prefix block lifetime、tail block eviction |
| 逐步分叉 | side table 的 `branch_factor` | 高 branch block 是否更少被驱逐 |
| 混合冷热 | `get_new_blocks()` 候选选择 | eviction regret、p95 latency |
| 长上下文压力 | free queue 长度与 `kv_cache_usage` | OOM/preemption、重算比例 |

可设置的对比组：

1. 原始 vLLM，prefix caching enabled。
2. 生命周期统计开启，但不改变驱逐策略。
3. 生命周期感知驱逐开启。
4. 若时间允许，增加 branch_factor 权重的消融实验。

---

## 12. 边界条件

### 12.1 Full-block 对齐

prefix cache 只缓存 full block。若公共前缀长度不是 block size 的整数倍，最后不足一个 block 的公共部分不会被命中。实验构造时应显式控制共享前缀长度，使其覆盖：

- 正好整 block；
- 整 block + 少量尾部；
- 在 block 中间分叉。

这样可以观察 full-block 粒度带来的收益和损失。

### 12.2 命中后最后 token 重算

即使 prompt 全命中，`get_computed_blocks()` 也会把最大命中限制为 `num_tokens - 1`，且按 block 对齐。这会导致一些看似全命中的 prompt 仍要重算最后一个 block。实验解释 TTFT 时必须考虑这一点。

### 12.3 ref_cnt 与 free queue 的关系

`ref_cnt == 0` 的 cached block 仍可能保留在 prefix cache hash map 中，并位于 free queue 里，等待未来 hit 或 eviction。prefix hit 时 `touch()` 会把它从 free queue 移出。驱逐策略只能作用于这类 `ref_cnt == 0` 的候选，不能动 `ref_cnt > 0` 的运行中 block。

### 12.4 多 KV cache group

`BlockPool.get_cached_block()` 要求每个 group 都命中，否则整个 group hit 失败。Hybrid coordinator 还会做 alignment。初始实验应避免混合 attention 模型，先使用普通 decoder-only 模型。

### 12.5 KV sharing fast prefill 不是本项目的跨请求 prefix cache

vLLM 还有 `kv_sharing_fast_prefill`，主要服务特定模型内部的层间 KV sharing 和 fast prefill metadata，不等同于本文关注的跨请求 KV block 前缀复用。初始实验无需依赖它。

---

## 13. 总结

从 vLLM v0.19.0 源码看，可行性报告提出的“KVCache 分配、复用与驱逐协同优化”具备明确工程落点。

综合源码结构和工程边界，较为可控的研究主线是：

1. 保持 vLLM 的 strict full-block prefix cache 和 append-only block table 不变；
2. 在 `BlockPool` 周围增加 block 生命周期 side table；
3. 先观测 prefix hit、ref count、free queue、eviction 和 rebuild；
4. 再在 `get_new_blocks()` 中加入二阶段候选评分；
5. 最后把链式 hash 暴露出的 parent-child 关系用于共享后分叉价值评估。

该路线能够回应可行性报告中的研究问题，同时将主要风险控制在 Python 层管理逻辑内，避免初始阶段进入 worker block table、attention metadata 和 kernel 等改动成本较高的区域。
