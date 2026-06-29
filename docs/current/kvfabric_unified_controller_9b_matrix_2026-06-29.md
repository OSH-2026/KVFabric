# KVFabric Unified Controller 与 Qwen3.5-9B 实验矩阵

日期：2026-06-29

## 结论

后续 9B 实验不再把 `shared_aware`、`family_protect`、`lru_admission` 当成互相割裂的外部策略。统一表述为：

- `KVFabric disabled`：只做 lifecycle 观测，行为等价 LRU。
- `KVFabric enabled, admission-dominant profile`：主吞吐/SLO goodput 调参入口。
- `KVFabric enabled, rebuilt-reduction profile`：用于验证 rebuilt-from-eviction 明显下降。
- `KVFabric enabled, latency-protected profile`：用于验证合适交互场景下 latency 下降。

旧 27B sticky conversation 结果只保留为历史背景，不作为 9B latency 结论。9B latency 需要重新跑 `interactive_latency_reuse` 系列实验。

## 统一 Controller 参数

新增统一控制向量，由 `KVFabricControlConfig` 读取，写入 lifecycle metrics 的 `controller` 字段：

```bash
KVFABRIC_ENABLE=1
KVFABRIC_PROFILE=admission_dominant

KVFABRIC_ADMISSION_STRENGTH=1.0
KVFABRIC_EVICTION_STRENGTH=0.0
KVFABRIC_SCHEDULER_STRENGTH=0.0
KVFABRIC_SLO_PROTECTION_STRENGTH=0.0
KVFABRIC_HINT_TRUST=1.0

KVFABRIC_LOW_REUSE_CACHE_FRACTION=0.0
KVFABRIC_TRANSIENT_CACHE_FRACTION=0.0
KVFABRIC_BYPASS_CACHE_FRACTION=0.0
KVFABRIC_DURABLE_CACHE_FRACTION=1.0
KVFABRIC_COLD_CACHE_FRACTION=0.0
```

旧 policy 名仍兼容，但正式报告优先使用 profile 和参数向量：

| 外部 policy/profile | 内部含义 | 主要用途 |
|---|---|---|
| `lru` / `off` | strength 全 0 | baseline |
| `kvfabric_admission` | admission=1, eviction=0, scheduler=0 | raw throughput / SLO goodput 主线 |
| `kvfabric_rebuilt` | admission 中等, eviction 低强度, scheduler=0 | rebuilt 下降验证 |
| `kvfabric_latency` | admission 中等, eviction 低强度, scheduler/SLO protection 打开 | latency 验证 |

## 算法改动

### Admission 改为连续 fraction

旧 admission 更接近 discovery-token/开关逻辑。现在变成：

```text
effective_fraction = 1 - ADMISSION_STRENGTH * (1 - class_fraction)
allowed_blocks = cached_blocks + ceil(new_blocks * effective_fraction)
allowed_blocks = max(allowed_blocks, anchor_or_discovery_blocks)
```

含义：

- `ADMISSION_STRENGTH=0`：等价全缓存。
- `ADMISSION_STRENGTH=1`：严格按 class fraction 缓存。
- `LOW_REUSE/BYPASS/TRANSIENT/COLD fraction=0`：只保留 anchor/discovery，不让低价值长 prompt 污染缓存。
- `DURABLE fraction=1`：稳定复用上下文全缓存。
- `HINT_TRUST=0`：忽略 hint，逐步回退为保守行为。

### Eviction 改为连续介入

`EVICTION_STRENGTH=0` 时完全 LRU。大于 0 时才扩大 candidate window，并用 retain score 跳过高价值块。

低强度时只保护明显有价值的 block，避免 9B 上之前出现的 shared-aware 过干预问题。默认 `kvfabric_rebuilt` 使用低强度 eviction，目标是降低 rebuilt，而不是把它作为 raw throughput 主路径。

### Scheduler 改为连续开关

`SCHEDULER_STRENGTH=0` 时 scheduler 完全不介入。latency profile 才打开 positive promotion 和 SLO protection。吞吐主实验默认不打开 scheduler，避免尾延迟/排队副作用污染 raw throughput 结论。

## 9B 完整 12h 矩阵

脚本：

```bash
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh
```

远程启动：

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh
```

完整矩阵按指标拆分：

| 模块 | 配置 | 容量 | policy | 单 policy workload | 目标 |
|---|---|---|---|---:|---|
| raw_prefill_throughput | `qwen3_5_9b_prefill_reuse_saturation_60m.json` | medium | `lru`, `kvfabric_admission` | 60m | raw total tok/s、req/s、prompt tok/s |
| slo_boundary_throughput | `qwen3_5_9b_saturation_reuse_proof_30m.json` | medium | `lru`, `kvfabric_admission` | 30m | SLO goodput 30%+ |
| rebuilt_pressure | `qwen3_5_9b_rebuilt_pressure_30m.json` | medium | `lru`, `kvfabric_rebuilt` | 30m | rebuilt-from-eviction 明显下降 |
| interactive_latency | `qwen3_5_9b_interactive_latency_reuse_45m.json` | medium | `lru`, `kvfabric_latency` | 45m | reusable interactive p95/e2e p95 latency 下降 |
| daily_dedicated | `qwen3_5_9b_daily_dedicated_reuse_40m.json` | medium | `lru`, `kvfabric_admission` | 40m | 日常高复用场景不劣化并争取收益 |
| capacity_sweep | `qwen3_5_9b_capacity_sweep_6m.json` | small/medium/large | `lru`, `kvfabric_admission` | 6m | 证明容量变化下收益趋势合理 |
| enterprise_normal | `qwen3_5_9b_enterprise_normal_25m.json` | medium | `lru`, `kvfabric_admission` | 25m | 普通企业混合场景不劣化 |
| low_reuse | `qwen3_5_9b_low_reuse_low_frequency_20m.json` | large | `lru`, `kvfabric_admission` | 20m | 低复用低频不劣化 |

纯 workload 合计约 8.9h。考虑每个 policy 需要重启 vLLM、生成 trace、汇总 metrics，完整跑完预计 11-12h。

## 短调参实验

脚本：

```bash
# raw overall token/s 调参，约 24-35 分钟含重启
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh throughput medium

# rebuilt 下降调参，约 24-35 分钟含重启
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh rebuilt medium

# latency 调参，约 24-35 分钟含重启
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh latency medium

# 容量趋势快速检查，约 70-100 分钟含重启
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh capacity
```

远程启动：

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_quick_loop_benchmark.sh throughput medium
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_quick_loop_benchmark.sh rebuilt medium
bash experiments/long_pressure_benchmark/scripts/run_remote_qwen3_5_9b_quick_loop_benchmark.sh latency medium
```

短实验和长实验一一对应：

| 短实验 | 长实验 |
|---|---|
| `qwen3_5_9b_prefill_reuse_quick_12m.json` | `qwen3_5_9b_prefill_reuse_saturation_60m.json` |
| `qwen3_5_9b_rebuilt_quick_12m.json` | `qwen3_5_9b_rebuilt_pressure_30m.json` |
| `qwen3_5_9b_interactive_latency_quick_12m.json` | `qwen3_5_9b_interactive_latency_reuse_45m.json` |

建议调参顺序：

1. 先跑 `throughput medium`，看 raw `total_tokens_per_second`、`requests_per_second`、prefix hit、SLO probe。
2. 再跑 `rebuilt medium`，调 `KVFABRIC_EVICTION_STRENGTH`、`KVFABRIC_EVICTION_RANK_MIN_SCORE`、candidate window，目标是 rebuilt 明显下降且 raw 不明显下降。
3. 再跑 `latency medium`，调 `KVFABRIC_SCHEDULER_STRENGTH` 和 `KVFABRIC_SLO_PROTECTION_STRENGTH`，目标是 reusable interactive 类 p95/e2e p95 下降，同时 cold/decode 不被饿死。
4. 参数稳定后只跑一次 12h matrix 收完整数据。

## 成功标准

不要把所有指标混成一句话。正式结论按模块写：

- raw throughput：`prefill_main` 或 overall scored raw `total_tokens_per_second` 目标 +30%；若达不到，不能写 raw overall +30%。
- SLO goodput：18/20/22/25s probes 中合适边界达到 +30%，并解释 SLO 边界。
- rebuilt：`rebuilt_from_eviction_blocks` 目标下降 30%-50% 以上，同时 prefix hit 或 warm family hit 有同步改善。
- latency：interactive reusable 类 p95/e2e p95 目标下降 30%，并要求 low-reuse/decode 类 p95 不劣化超过 10%-15%。
- generalization：enterprise normal、low reuse、large capacity 下不明显劣化。
