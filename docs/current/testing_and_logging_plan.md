# 当前测试、日志与复跑方案

本文档描述 KVFabric 当前已经可运行的测试链路，以及最终收尾阶段建议保留的复跑和日志证据。

## 当前已可运行的测试

### vLLM baseline 与普通预验证

- `offline_batch`：离线批量请求，验证模型加载、批处理和结果落盘。
- `online_batch`：在线 OpenAI-compatible API 顺序请求，记录平均延迟、p50、p95 和 token 数。
- `prefix_reuse_smoke`：小规模共享前缀 smoke，确认服务路径可用。
- `medium_prefix_reuse`：中等规模共享前缀测试，观察 prefix hit rate。
- `soak_prefix_reuse_20min`：长时间共享前缀请求，用于稳定性和日志通路观察。

### KVFabric A/B

- `run_kvfabric_ab_smoke.sh`：默认跑 `lru` 与 `family_protect` 两组。
- `summarize_kvfabric_lifecycle.py`：汇总 lifecycle JSONL。
- `compare_kvfabric_ab.py`：生成 LRU vs KVFabric Markdown 对比。
- `compare_kvfabric_ablation.py`：对 retain score 消融结果做汇总。

### 长时间对话压测

`experiments/langtime_running_test/` 已提供：

- `continuous`：持续追问。
- `random_topic`：随机话题。
- `persona_rotation`：角色轮换。
- `dataset_driven`：数据集驱动。
- `pressure_test`：并发压力。
- `multi_turn_fork`：多轮分叉。

这条线用于构造更接近真实长对话和多轮分叉的 KV reuse 场景。

## 当前日志链路

KVFabric 当前有两类日志/指标。

### JSONL lifecycle events

通过环境变量开启：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
```

主要事件：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `eviction_candidates_ranked`
- `block_evicted`

事件只记录 hash、block id、token 数、状态和指标，不记录 prompt 明文或 KV tensor。

### Prometheus metrics

通过 `vllm_baseline/scripts/read_metrics.sh` 读取 `/metrics`，当前 A/B 脚本会保存：

```text
prometheus_metrics_summary.json
prometheus_metrics_summary.txt
```

关注指标：

- request hit rate；
- prefix token hit rate；
- saved prefill tokens proxy；
- KV block lookup hit rate；
- eviction regret rate；
- TTFT / TPOT / E2E latency；
- metadata update overhead；
- KV lookup overhead。

## 已观察到的关键现象

在 `qwen3_5_2b`、`max_model_len=1024`、`ENABLE_PREFIX_CACHING=1` 下：

- 共享前缀不足一个 full block 时，prefix cache hit rate 仍可能为 0。
- 共享系统前缀足够长后，`medium_prefix_reuse` 可以观察到明显 prefix hit。
- 无 cached eviction 时，KVFabric 通过 fast path 退化回 vLLM 原路径。
- 普通无共享请求中，`family_protect` 基本不触发 protected deferral。
- 模板 family 回访和相似多轮场景中，`family_protect` 能减少共享主干误驱逐，提高 prefix-hit tokens。

## 推荐最终复跑矩阵

### 1. 普通无共享场景

配置：

```text
experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
```

目的：

- 验证普通 serving 场景中 KVFabric 不明显掉速；
- 验证 prefix-hit tokens 和 rebuilt-from-eviction 都应接近 0；
- 验证 eviction ranking events 不应异常增加。

### 2. 模板 family 单周期回访

配置：

```text
experiments/prebenchmark_validation/configs/template_family_revisit.json
```

建议参数：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

目的：

- 验证模板化 prompt 场景下共享主干保护；
- 观察 rebuilt-from-eviction、shared-anchor eviction ratio、prefix-hit tokens 和 TTFT。

### 3. 模板 family 多周期回访

配置：

```text
experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

目的：

- 更接近多轮对话或周期性回访；
- 验证策略在多轮冷压力/热回访交替下是否稳定。

### 4. 三组对照，可选但推荐

最终报告最好补齐：

1. prefix caching off；
2. prefix caching on + LRU；
3. prefix caching on + `family_protect`。

这样可以区分“vLLM prefix caching 本身收益”和“KVFabric 生命周期策略增益”。

## 结果文件要求

每个代表性 run 建议保留：

```text
<run>/
├─ lru/
│  ├─ online/metrics.json
│  ├─ kvfabric_lifecycle.jsonl
│  ├─ kvfabric_lifecycle_metrics.json
│  └─ prometheus_metrics_summary.json
├─ family_protect/
│  ├─ online/metrics.json
│  ├─ kvfabric_lifecycle.jsonl
│  ├─ kvfabric_lifecycle_metrics.json
│  └─ prometheus_metrics_summary.json
└─ ab_comparison.md
```

如果原始 JSONL 太大，可以只保留 summary JSON 和 Markdown，对原始路径做说明。

## 报告解释原则

最终报告中建议按三层解释结果：

1. 行为指标：是否减少 protected/shared-anchor block 误驱逐。
2. 复用指标：prefix-hit tokens、rebuilt-from-eviction 是否改善。
3. 服务指标：TTFT、E2E latency、requests/s 是否改善或至少不过度退化。

不要只用单一 requests/s 判断项目成败。KVFabric 当前 prototype 的主要价值是让 KVCache 资源管理更可观测、更可解释，并在长期复用结构明显的 workload 中减少错误驱逐和重复 prefill。
