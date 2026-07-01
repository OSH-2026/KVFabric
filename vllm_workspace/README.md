# vLLM Overlay 源码工作区

本目录维护 KVFabric 对 vLLM 0.22.1 Python 控制面的 overlay。运行时通过脚本将 overlay 应用到 `.venv` 或指定的 vLLM 源码树。

## 工作区定位

KVFabric 保留 vLLM 的 worker、attention kernel、PagedAttention 和物理 KV block 语义，在 Python 控制面增加资源管理信息和策略入口。overlay 主要覆盖：

- lifecycle side table；
- Prefix Family 元数据；
- JSONL lifecycle event logger；
- Prometheus metrics probe；
- shared-aware eviction；
- family-protect 共享主干保护；
- hint-aware admission；
- scheduler affinity 和 latency guard；
- request metadata / header plumbing；
- SLO goodput、class metrics 和实验 summary 支撑。

这种工作流便于与官方 vLLM 对齐，也方便在 baseline 环境和 KVFabric 环境之间切换。

## 推荐流程

1. 在 `vllm_workspace/overlay/` 中维护改动。
2. 使用 `diff_to_patch.sh` 导出 patch。
3. 使用 `apply_to_worktree.sh` 应用到当前 `.venv` 或指定 vLLM 工作树。
4. 通过 `experiments/prebenchmark_validation/` 跑本地 smoke。
5. 通过 `experiments/long_pressure_benchmark/` 跑远程 9B 中等实验或 12h 矩阵。
6. 根据 lifecycle JSONL、Prometheus、summary 和 dashboard 判断策略行为。

默认上游位置会自动解析为当前项目 `.venv` 中安装的 vLLM；也可以用 `VLLM_UPSTREAM_ROOT` 指定完整源码树：

```bash
VLLM_UPSTREAM_ROOT=/path/to/vllm-source \
bash vllm_workspace/scripts/apply_to_worktree.sh
```

## 当前关注文件

```text
vllm/v1/core/block_pool.py
vllm/v1/core/kv_cache_manager.py
vllm/v1/core/single_type_kv_cache_manager.py
vllm/v1/core/kv_cache_coordinator.py
vllm/v1/core/kv_cache_utils.py
vllm/v1/core/kv_cache_metrics.py
vllm/v1/core/kvfabric_lifecycle.py
vllm/v1/core/kvfabric_family.py
vllm/v1/core/kvfabric_hints.py
vllm/v1/core/sched/scheduler.py
vllm/v1/core/sched/output.py
vllm/v1/engine/async_llm.py
vllm/v1/metrics/loggers.py
vllm/v1/metrics/stats.py
vllm/entrypoints/openai/*
```

这些文件覆盖 prefix cache 命中、block 分配、cache 写入、free queue、驱逐、请求元数据、调度输出和 metrics，是 KVFabric 当前的核心改造位置。

## Lifecycle 模块

核心模块：

```text
vllm/v1/core/kvfabric_lifecycle.py
```

主要对象：

- `LifecycleBlockMeta`：记录 block hash、prefix depth、ref count、hit count、share degree、branch factor、recompute cost、state 和 retain score。
- `EvictedShadow`：记录被驱逐 block 的摘要，用于识别后续 rebuilt-from-eviction。
- `KVFabricLifecycleTracker`：维护 side table、事件日志、retain score、protected 判断、admission 状态和 scheduler hook 数据。

当前实现记录 family 和 branch 的近似控制面信息，用于策略和指标解释。它没有实现 token 级 trie，也没有保存每个 child branch 的完整权重分布或每个 request 的去重共享集合。

## Unified Controller

6 月下旬后，策略配置逐步从单个策略名收敛为 controller 参数。推荐从四个维度理解：

| 维度 | 作用 |
| --- | --- |
| Admission | 控制哪些请求和哪些深度的 block 进入 prefix cache，减少 cold / low-reuse churn |
| Eviction | 控制驱逐候选的 retain score、共享保护和 family-protect 强度 |
| Schedule | 控制 waiting queue 中高 prefix-hit 请求的 promotion |
| SLO protect | 控制 foreground、decode-heavy、低复用和长输出请求的 age/defer guard |

stage-local preset 只表示某个实验阶段对这些维度的强调，不代表不同代码路径。

## 常用环境变量

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
KVFABRIC_EVICTION_POLICY=lru|shared_aware|family_protect
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_PROTECT_MIN_SHARE_DEGREE=2
KVFABRIC_PROTECT_MIN_BRANCH_FACTOR=1
KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS=800
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
KVFABRIC_HINTS=1
KVFABRIC_HINT_ADMISSION=1
KVFABRIC_HINT_SCHEDULER=1
KVFABRIC_RANK_LOG_CANDIDATES=0|1
```

远程 9B 矩阵通常通过脚本设置完整 controller 参数，避免手动环境变量漂移。

## JSONL 事件

常见事件包括：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `request_hints_observed`
- `request_deferred`
- `eviction_candidates_ranked`
- `block_evicted`
- `lifecycle_reset`

事件用于解释策略行为，不记录 prompt 明文和 KV tensor。

## 指标探针

overlay 扩展了 vLLM metrics，能够通过 `/metrics` 和 summary 脚本读取：

- prefix cache request hit rate；
- prefix token hit rate；
- KV block lookup hit rate；
- allocations、cached blocks、evictions 和 free blocks；
- active / peak active blocks；
- recompute cost proxy；
- branch factor；
- eviction regrets 和 rebuild gap；
- metadata update time；
- waiting queue time / size；
- class latency、segment throughput 和 SLO goodput。

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

## 验证入口

本地短验证：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

远程 9B 矩阵：

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh
```

## 当前结论

当前 overlay 已经支持真实 vLLM 控制面的 lifecycle 事件闭环、共享感知驱逐、hint-aware admission、scheduler promotion、latency guard 和长测指标输出。收益主要体现在 eviction quality、rebuilt-from-eviction、prefix-hit tokens、SLO goodput 和部分请求级延迟上。后续仍可继续推进 token 级 trie、真实 CoW、跨请求物理 block 去重和更深的 scheduler 改造。
