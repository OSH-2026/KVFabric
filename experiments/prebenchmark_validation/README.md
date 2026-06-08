# Prebenchmark Validation

本目录承接 KVFabric 当前阶段的真实 vLLM serving 验证。它不再只是 baseline 后的 prefix caching smoke test，也承担 KVFabric lifecycle prototype 的小到中等规模 A/B 验收。

当前职责：

- 验证 vLLM online/offline 请求链路；
- 验证 prefix caching 是否能在共享前缀场景中命中；
- 收集 lifecycle JSONL 事件；
- 汇总 Prometheus metrics；
- 比较 vLLM LRU 路径与 KVFabric `family_protect` / `shared_aware` 策略；
- 为最终报告提供少量可复现代表性结果。

## 目录结构

```text
prebenchmark_validation/
├─ README.md
├─ configs/                         # workload 配置
├─ examples/                        # online/offline 请求、summary、A/B 对比脚本
├─ runs/                            # 真实运行输出，默认不提交大量原始结果
└─ scripts/                         # shell 入口
```

## 普通预验证入口

从仓库根目录开始：

```bash
cd KVFabric

bash experiments/prebenchmark_validation/scripts/run_offline_batch.sh qwen3_5_2b

bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_online_batch.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_prefix_reuse_smoke.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

这些入口用于确认服务路径、prefix caching 和日志摘要正常。

## KVFabric A/B 入口

运行 LRU vs KVFabric policy：

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

默认策略组：

```text
lru family_protect
```

可以通过环境变量覆盖：

```bash
KVFABRIC_AB_POLICIES="lru shared_aware family_protect" \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/cache_pressure_ambiguous_hot_revisit.json
```

每个 policy 会执行：

1. 停止旧 vLLM 服务；
2. 设置 `KVFABRIC_LIFECYCLE=1` 和 `KVFABRIC_EVICTION_POLICY=<policy>`；
3. 启动 vLLM 服务；
4. 跑 `online_batch.py`；
5. 抓取 Prometheus metrics；
6. 停止服务；
7. 汇总 `kvfabric_lifecycle.jsonl`。

## A/B 汇总

生成 Markdown 对比报告：

```bash
python experiments/prebenchmark_validation/examples/compare_kvfabric_ab.py \
  <run-dir> \
  --candidate family_protect \
  --output <run-dir>/ab_comparison.md
```

汇总单个 lifecycle JSONL：

```bash
python experiments/prebenchmark_validation/examples/summarize_kvfabric_lifecycle.py \
  --input <run-dir>/<policy>/kvfabric_lifecycle.jsonl \
  --output <run-dir>/<policy>/kvfabric_lifecycle_metrics.json
```

## 推荐代表性场景

### 1. 普通无共享请求

```text
configs/ordinary_unique_cold.json
```

用途：

- sanity check；
- 验证 KVFabric 在没有长期共享前缀的普通 serving 场景下不明显掉速；
- 预期 prefix-hit tokens 和 rebuilt-from-eviction 接近 0；
- `family_protect` 不应产生大量 ranking events。

建议参数：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=3
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

### 2. 模板 family 单周期回访

```text
configs/template_family_revisit.json
```

用途：

- 验证模板化 prompt / 相似多轮场景中的共享主干保护；
- 观察 shared-anchor eviction ratio、rebuilt-from-eviction、prefix-hit tokens、TTFT 和 requests/s。

建议参数：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

### 3. 模板 family 多周期回访

```text
configs/template_family_revisit_cycles.json
```

用途：

- 更接近长期多轮回访；
- 每轮冷请求冲刷后再回访长期模板 family；
- 用于最终报告的重点场景。

建议参数：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

### 4. 冷热混淆高压回访

```text
configs/cache_pressure_ambiguous_hot_revisit.json
```

用途：

- 验证策略能否区分短期冷共享与长期热点 family；
- 更适合观察 eviction quality，而不是追求稳定吞吐提升。

## 输出结构

A/B 运行输出：

```text
runs/<timestamp>_<preset>_<suite>_kvfabric_ab/
├─ lru/
│  ├─ online/
│  │  ├─ config.json
│  │  ├─ env.json
│  │  ├─ raw_outputs.jsonl
│  │  ├─ metrics.json
│  │  └─ summary.md
│  ├─ kvfabric_lifecycle.jsonl
│  ├─ kvfabric_lifecycle_metrics.json
│  ├─ prometheus_metrics_summary.json
│  └─ prometheus_metrics_summary.txt
├─ family_protect/
│  └─ ...
└─ ab_comparison.md
```

普通 online/offline 运行输出：

```text
runs/<timestamp>_<preset>_<experiment>/
├─ env.json
├─ config.json
├─ raw_outputs.jsonl
├─ metrics.json
└─ summary.md
```

`runs/` 下的大量原始结果默认不建议全部提交。最终交付时可以挑选代表性结果，或只提交整理后的 Markdown/JSON summary。

## 当前关键指标

Lifecycle summary:

- `prefix_hit_tokens`
- `prefix_hit_rate`
- `sealed_blocks`
- `touched_blocks`
- `evicted_blocks`
- `shared_anchor_eviction_ratio`
- `protected_eviction_ratio`
- `rebuilt_from_eviction_blocks`
- `avg_evicted_retain_score`
- `cache_admission_saved_blocks`

Prometheus summary:

- request hit rate；
- prefix token hit rate；
- saved prefill tokens proxy；
- recompute ratio proxy；
- KV block lookup hit rate；
- KV block eviction regret rate；
- TTFT / TPOT / E2E latency；
- metadata update overhead；
- KV lookup overhead。

Online metrics:

- requests/s；
- average latency；
- p50 / p95 latency；
- prompt tokens；
- completion tokens；
- completion tokens/s。

## 结果解释原则

当前 KVFabric prototype 的收益应该按场景解释：

- 普通无共享请求：目标是低开销退化，不追求 prefix-hit 提升。
- 模板化 prompt / 相似多轮：目标是保护共享主干，减少 rebuilt-from-eviction，提高 prefix-hit tokens。
- cache pressure：重点看 eviction quality 和策略开销，不应只看 requests/s。

最终报告中不要把合成闭环或模板 workload 的收益泛化为所有 workload 通用吞吐提升。当前更准确的结论是：KVFabric 改善了长期复用结构明显场景下的 KVCache 资源管理质量。
