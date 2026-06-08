# vLLM Overlay 源码工作区

本目录用于管理 KVFabric 对 vLLM Python 控制面的原型改造。它不是一个可直接导入的完整 `vllm` 包，而是一组 overlay 文件：在这里维护局部改动，需要真实运行时再显式应用到 `.venv` 或完整 vLLM 源码树。

当前 overlay 已经不只是观测探针，而是包含：

- KVFabric lifecycle side table；
- JSONL lifecycle event logger；
- Prometheus metrics probe；
- `shared_aware` retain-score 驱逐策略；
- `family_protect` 共享主干保护策略；
- request-aware / length-aware admission control；
- 与 A/B 实验脚本对接的指标输出。

## 工作流定位

采用 overlay 的原因是避免把半成品 vLLM 源码直接作为完整包导入，造成缺文件或运行行为混乱。

推荐流程：

1. 在 `vllm_workspace/overlay/` 中维护改动。
2. 使用 `diff_to_patch.sh` 导出 patch。
3. 使用 `apply_to_worktree.sh` 应用到当前 `.venv` 或指定 vLLM 工作树。
4. 通过 `experiments/prebenchmark_validation/` 运行 A/B。
5. 验证结束后确认运行环境是否需要恢复为干净 vLLM。

默认上游位置会自动解析为当前项目 `.venv` 中安装的 vLLM；也可以用 `VLLM_UPSTREAM_ROOT` 指定完整源码树：

```bash
VLLM_UPSTREAM_ROOT=/path/to/vllm-source \
bash vllm_workspace/scripts/apply_to_worktree.sh
```

## 当前关注文件

```text
vllm/v1/core/block_pool.py
vllm/v1/core/kv_cache_manager.py
vllm/v1/core/kvfabric_lifecycle.py
vllm/v1/core/kv_cache_metrics.py
vllm/v1/core/kv_cache_utils.py
vllm/v1/core/single_type_kv_cache_manager.py
vllm/v1/core/kv_cache_coordinator.py
vllm/v1/core/sched/scheduler.py
vllm/v1/core/sched/output.py
vllm/v1/metrics/loggers.py
vllm/v1/metrics/stats.py
```

这些文件覆盖 prefix cache 命中、block 分配、free queue、驱逐、KV cache 统计和调度输出，是 KVFabric lifecycle prototype 的核心位置。

## Lifecycle 模块

核心新增模块：

```text
vllm/v1/core/kvfabric_lifecycle.py
```

主要对象：

- `LifecycleBlockMeta`：记录 block hash、prefix depth、ref count、hit count、share degree、branch factor、recompute cost、state。
- `EvictedShadow`：记录被驱逐 block 的摘要，用于识别后续 rebuilt-from-eviction。
- `KVFabricLifecycleTracker`：维护 side table、事件日志、retain score、protected 判断、family protect 选择器和 admission gate。

## 策略开关

常用环境变量：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
KVFABRIC_EVICTION_POLICY=lru|shared_aware|family_protect
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_PROTECT_MIN_SHARE_DEGREE=2
KVFABRIC_PROTECT_MIN_BRANCH_FACTOR=1
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
KVFABRIC_RANK_LOG_CANDIDATES=0|1
```

策略说明：

- `lru`：只记录 lifecycle，不改变 vLLM 原驱逐顺序。
- `shared_aware`：对候选窗口计算 retain score，选择最低保留价值 block。
- `family_protect`：保持 LRU 顺序，遇到 protected shared-family block 时延后驱逐。

## 已加入的事件

JSONL 事件包括：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `eviction_candidates_ranked`
- `block_evicted`
- `lifecycle_reset`

事件用于解释策略行为，不记录 prompt 明文和 KV tensor。

## 已加入的指标探针

当前 overlay 扩展了 vLLM metrics，能通过 `/metrics` 与 `read_metrics.sh` 读取：

- `vllm:prefix_cache_requests_total`
- `vllm:prefix_cache_request_hits_total`
- `vllm:kv_block_lookup_queries_total`
- `vllm:kv_block_lookup_hits_total`
- `vllm:kv_block_allocations_total`
- `vllm:kv_block_cached_total`
- `vllm:kv_block_evictions_total`
- `vllm:kv_block_free`
- `vllm:kv_block_total`
- `vllm:kv_block_active`
- `vllm:kv_block_peak_active`
- `vllm:kv_block_cached_entries`
- `vllm:kv_block_access_count_before_evict`
- `vllm:kv_block_peak_ref_count`
- `vllm:kv_block_cache_depth_blocks`
- `vllm:kv_block_recompute_cost_tokens`
- `vllm:kv_block_branch_factor`
- `vllm:kv_block_eviction_regrets_total`
- `vllm:kv_block_rebuild_gap_seconds`
- `vllm:kv_block_lookup_time_seconds`
- `vllm:kv_metadata_update_time_seconds`
- `vllm:kv_waiting_time_seconds`
- `vllm:kv_waiting_requests`

## 常用命令

```bash
cd KVFabric

# 从当前 .venv 的 vLLM 同步 overlay。注意：会覆盖 overlay 中的改动。
bash vllm_workspace/scripts/sync_from_upstream.sh

# 导出 overlay 相对当前 vLLM 的 patch。
bash vllm_workspace/scripts/diff_to_patch.sh

# 将 overlay 应用到当前 .venv 或 VLLM_UPSTREAM_ROOT 指定的 vLLM 工作树。
bash vllm_workspace/scripts/apply_to_worktree.sh
```

## 静态检查

```bash
python3 -m py_compile \
  vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py \
  vllm_workspace/overlay/vllm/v1/core/block_pool.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_utils.py \
  vllm_workspace/overlay/vllm/v1/metrics/loggers.py \
  vllm_workspace/overlay/vllm/v1/metrics/stats.py
```

```bash
bash -n vllm_workspace/scripts/apply_to_worktree.sh
bash -n vllm_workspace/scripts/diff_to_patch.sh
bash -n vllm_workspace/scripts/sync_from_upstream.sh
```

## 推荐验证

普通无共享场景：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=3 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
```

模板 family 多周期回访：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

## 当前结论

当前 overlay 已经支持真实 vLLM 控制面的 lifecycle 事件闭环和初步策略验证。更稳妥的阶段性结论是：

- 普通无共享场景中，KVFabric 能低开销退化。
- 模板化 prompt、相似多轮和长期 family 回访场景中，`family_protect` 能降低共享主干误驱逐。
- 当前 prototype 的收益主要体现在 eviction quality、rebuilt-from-eviction、prefix-hit tokens 和部分请求级指标上。
- 非严格 chunk 级共享、真实 CoW、显式 prefix-family tree 和 scheduler 改调度尚未实现。
