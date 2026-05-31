# vLLM Overlay 源码工作区

本目录用于管理 vLLM v0.19.1 的 Python 控制面改造准备。

它不是一个可直接导入的 `vllm` Python 包，也不应该通过
`PYTHONPATH` 覆盖当前安装的 vLLM。这里采用 overlay 工作流：只把后续
最可能修改的核心文件复制进当前项目，方便阅读、diff 和 patch 管理；
真正运行时再显式应用到完整的 vLLM 安装目录或源码树。

默认上游位置会自动解析为当前项目 `.venv` 中安装的 vLLM：

```text
KVFabric/.venv/lib/python*/site-packages
```

如果要对完整源码 checkout 操作，可以用 `VLLM_UPSTREAM_ROOT` 显式指定：

```bash
VLLM_UPSTREAM_ROOT=/path/to/vllm-source bash vllm_workspace/scripts/diff_to_patch.sh
```

## 使用 Overlay 的原因

如果只复制一部分 `vllm/` 包到 `KVFabric` 并直接导入，很容易遮蔽完整安装包，导致缺文件、导入混乱或运行时行为不一致。

Overlay 的好处是：

- 当前项目只管理后续要关注的核心文件；
- 不把半成品源码伪装成完整 vLLM 包；
- 可以清楚比较 upstream 与本地改动；
- 后续能导出 patch 或临时应用到运行环境验证。

## 当前关注文件

当前 overlay 聚焦 Python 控制面：

- `vllm/v1/core/block_pool.py`
- `vllm/v1/core/kv_cache_manager.py`
- `vllm/v1/core/kv_cache_metrics.py`
- `vllm/v1/core/kv_cache_utils.py`
- `vllm/v1/core/single_type_kv_cache_manager.py`
- `vllm/v1/core/kv_cache_coordinator.py`
- `vllm/v1/core/sched/scheduler.py`
- `vllm/v1/core/sched/output.py`
- `vllm/v1/metrics/loggers.py`
- `vllm/v1/metrics/stats.py`

这些文件覆盖 prefix cache 命中、block 分配、free queue、驱逐、KV cache 统计和调度输出，是后续添加生命周期日志和共享感知策略的优先位置。

## 已加入的指标探针

当前 overlay 只增加观测指标，不改变调度、分配或驱逐策略。

已暴露到 Prometheus 的新增指标包括：

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

其中 `kv_block_eviction_regrets_total` 的语义是：采样到的 block 被驱逐后，
后续又出现同一个 block hash 被重建。这个指标需要专门构造“驱逐后再次请求
同一前缀”的 workload 才容易非零。

## 常用命令

```bash
cd KVFabric

# 从当前 .venv 的 vLLM 同步 overlay。注意：这会覆盖 overlay 中的改动。
bash vllm_workspace/scripts/sync_from_upstream.sh

# 导出 overlay 相对当前 .venv vLLM 的 patch。
bash vllm_workspace/scripts/diff_to_patch.sh

# 将 overlay 应用到当前 .venv vLLM。只在准备真实运行验证时使用。
bash vllm_workspace/scripts/apply_to_worktree.sh
```

建议流程：

1. 确认 `.venv` 中的 vLLM 是干净基线。
2. 在 overlay 中做小步修改。
3. 运行静态检查和 diff 审查。
4. 临时应用到 `.venv` 或完整源码树。
5. 启动 vLLM 服务验证 `/metrics`。
6. 验证结束后恢复运行环境，避免 `.venv` 长期处于手改状态。

## 验证命令

静态检查：

```bash
python3 -m py_compile \
  vllm_workspace/overlay/vllm/v1/core/block_pool.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py \
  vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py \
  vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py \
  vllm_workspace/overlay/vllm/v1/metrics/loggers.py \
  vllm_workspace/overlay/vllm/v1/metrics/stats.py

bash -n vllm_baseline/scripts/read_metrics.sh
git diff --check -- vllm_workspace vllm_baseline/scripts/read_metrics.sh
```

临时应用并启动小模型：

```bash
bash vllm_workspace/scripts/apply_to_worktree.sh
bash vllm_baseline/scripts/serve_local.sh qwen2_5_0_5b
```

读取指标摘要：

```bash
bash vllm_baseline/scripts/read_metrics.sh --text
```

停止服务：

```bash
bash vllm_baseline/scripts/stop_server.sh qwen2_5_0_5b
```

如果只是临时验证，结束后建议重新安装或从备份恢复 `.venv` 中的 vLLM 文件，
再用 wheel `RECORD` 或重新安装确认运行环境回到干净状态。

## 最近一次验证结果

最近一次在 `qwen2_5_0_5b`、`KV_CACHE_METRICS=1`、
`KV_CACHE_METRICS_SAMPLE=1.0` 下验证通过。

共享前缀和压力请求后，读到的关键指标包括：

```text
prefix_cache_requests           100
prefix_cache_request_hits       19
prefix_cache_queries            63050
prefix_cache_hits               3952
kv_block_lookup_queries         328
kv_block_lookup_hits            247
kv_block_allocations            3733
kv_block_cached                 3633
kv_block_evictions_total        565
block_lifetime samples          565
block_recompute_cost samples    565
block_lookup_time samples       100
metadata_update_time samples    220
```

这说明新增指标可以在真实 vLLM 服务中通过 `/metrics` 暴露。该次 workload 没有
触发 eviction regret，所以 `kv_block_eviction_regrets_total` 为 0。
