# Evaluation Plan

本文档描述 KVFabric 当前阶段的评测计划。当前项目已经从官方 vLLM baseline 进入 vLLM Python 控制面 lifecycle prototype，因此评测重点也从“是否能跑通 vLLM”转为“生命周期策略是否改善 KVCache 资源管理质量，并且开销是否可接受”。

## 评测目标

当前评测要回答四个问题：

1. vLLM baseline 是否稳定可复现；
2. prefix caching 是否能在共享 full-block 前缀场景中命中；
3. KVFabric lifecycle prototype 是否能减少共享主干误驱逐和 rebuilt-from-eviction；
4. 策略开销是否会抵消收益，普通无共享场景能否低开销退化。

## 对比组

### 1. vLLM baseline

用于验证基本服务能力和提供参考基线：

- offline inference；
- OpenAI-compatible online serving；
- prefix caching off / on；
- request latency、tokens/s、KV cache usage。

### 2. LRU + lifecycle observe

运行真实 vLLM 原驱逐路径，同时打开 KVFabric lifecycle 日志：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_EVICTION_POLICY=lru
```

用途：

- 记录 prefix lookup、block sealed、touch、evict、rebuilt-from-eviction；
- 与 `family_protect` 做行为对照；
- 验证观测层不改变策略。

### 3. KVFabric family-protect

当前主要 candidate：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_EVICTION_POLICY=family_protect
```

用途：

- 保护长期复用的共享前缀主干；
- 减少 shared-anchor eviction；
- 降低 rebuilt-from-eviction；
- 在模板化、多轮和长期回访场景中提升 prefix-hit tokens。

### 4. KVFabric shared-aware

作为策略因子和消融分析用：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_EVICTION_POLICY=shared_aware
```

用途：

- 验证 retain score 的 reuse、prefix position、recompute cost 等因子；
- 解释 shared-aware ranking 逻辑；
- 与更轻量的 `family_protect` 做开销对比。

## Workloads

### 1. Ordinary Unique Cold

配置：

```text
experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
```

目标：

- 验证普通无共享请求中 KVFabric 不明显掉速；
- 确认 prefix-hit tokens、rebuilt-from-eviction 接近 0；
- 确认 family protection 不应频繁触发。

### 2. Prefix Reuse Smoke / Medium Prefix Reuse

配置：

```text
prefix_reuse_smoke.json
medium_prefix_reuse.json
```

目标：

- 验证 prefix caching 是否开启；
- 确认 full-block 边界；
- 观察共享前缀足够长时的 prefix hit 行为。

### 3. Template Family Revisit

配置：

```text
experiments/prebenchmark_validation/configs/template_family_revisit.json
```

目标：

- 验证模板化 prompt 中共享主干保护；
- 观察 LRU 是否误驱逐长期 family；
- 比较 prefix-hit tokens、rebuilt-from-eviction、TTFT 和 requests/s。

### 4. Template Family Revisit Cycles

配置：

```text
experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

目标：

- 模拟多周期冷压力与热点 family 回访；
- 更接近相似多轮对话或周期性模板请求；
- 作为最终报告中的重点场景。

### 5. Cache Pressure

配置：

```text
cache_pressure_hot_cold.json
cache_pressure_phased_hot_revisit.json
cache_pressure_ambiguous_hot_revisit.json
```

目标：

- 制造 KV eviction；
- 观察 shared-anchor eviction、protected eviction 和 rebuilt-from-eviction；
- 验证策略能否区分短期冷共享与长期热点 family。

### 6. Long-Dialogue Stress Test

目录：

```text
experiments/langtime_running_test/
```

目标：

- 构造长时间对话、多轮分叉、persona rotation、dataset-driven 和 pressure test；
- 为后续长上下文、多轮历史复用和真实对话形态提供 workload。

## Metrics

### 请求级指标

- requests/s；
- average latency；
- p50 / p95 latency；
- TTFT；
- TPOT；
- E2E latency；
- prompt tokens；
- completion tokens；
- completion tokens/s。

### Prefix 复用指标

- request hit rate；
- prefix token hit rate；
- prefix-hit tokens；
- saved prefill tokens proxy；
- recompute ratio proxy。

### 生命周期与驱逐指标

- sealed blocks；
- touched blocks；
- evicted blocks；
- shared-anchor eviction ratio；
- protected eviction ratio；
- avg evicted retain score；
- rebuilt-from-eviction blocks；
- regretful eviction proxy；
- cache admission saved blocks。

### 策略开销指标

- metadata update time；
- KV block lookup time；
- ranking events；
- selected protected ratio；
- waiting time / waiting requests。

## 推荐最终矩阵

最终报告至少保留：

| 场景 | 对照组 | 目的 |
| --- | --- | --- |
| ordinary unique cold | LRU vs family-protect | 普通场景无害 |
| template family revisit | LRU vs family-protect | 模板单周期共享主干保护 |
| template family revisit cycles | LRU vs family-protect | 多周期回访收益 |

如果时间允许，补充：

| 场景 | 对照组 | 目的 |
| --- | --- | --- |
| template family revisit cycles | prefix off / prefix on LRU / family-protect | 区分 prefix caching 本身收益与 KVFabric 增益 |
| ambiguous hot revisit | LRU / shared-aware / family-protect | 验证策略因子与开销 |

## 结果解释原则

最终结论应分场景解释：

- 普通无共享场景：目标是低开销退化。
- 模板化和相似多轮场景：目标是减少共享主干误驱逐和重复 prefill。
- Cache pressure 场景：重点看 eviction quality，而不是只看 throughput。
- 长时间对话场景：重点验证 workload 生成和多轮 KV reuse 结构。

当前阶段不应把 KVFabric 描述成所有 workload 的通用吞吐加速器。更准确的表述是：KVFabric 通过生命周期观测和 family-aware 策略改善长期复用结构明显场景下的 KVCache 资源管理质量。
