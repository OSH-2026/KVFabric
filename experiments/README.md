# Experiments

`experiments/` 统一管理 KVFabric 的实验资产。当前结构覆盖本地 smoke test、早期 A/B、纯 Python 生命周期策略闭环、长对话压测、远程 9B/27B 长周期实验、论文复现和结果可视化工具。

## 目录结构

```text
experiments/
├─ prebenchmark_validation/        # 早期真实 vLLM smoke、短验证和历史 A/B run
├─ long_pressure_benchmark/        # 远程长周期实验、9B 最终矩阵、dashboard/replay
├─ benchmarks/
│  └─ lifecycle_policy/            # 纯 Python 生命周期策略最小闭环
├─ langtime_running_test/          # 长时间对话、多轮分叉和压力测试
└─ paper_reproductions/            # 性能/质量评测复现与扩展
```

## 当前实验分层

### 1. 本地 smoke 与短验证

入口：`prebenchmark_validation/`

用途：

- 验证 overlay 是否能应用到 vLLM。
- 检查 lifecycle JSONL、Prometheus metrics 和 summary 是否完整。
- 跑普通无共享、模板 family、cache pressure 等小规模 A/B。
- 作为远程实验前的功能回归入口。

### 2. 策略解释闭环

入口：`benchmarks/lifecycle_policy/`

用途：

- 用纯 Python 合成闭环解释 lifecycle side table、retain score、LRU vs shared-aware 和 eviction regret。
- 输出稳定、可控、易解释的策略行为。
- 不直接用于宣称真实 GPU 性能收益。

### 3. 长对话与多轮压力

入口：`langtime_running_test/`

用途：

- 构造 continuous、random topic、persona rotation、dataset-driven、pressure test、multi-turn fork 等对话模式。
- 观察长上下文、多轮分叉和共享前缀在请求级别的行为。
- 为 9B trace 设计提供早期 workload 参考。

### 4. 远程长周期实验

入口：`long_pressure_benchmark/`

用途：

- 在远程 2 x RTX 3090 服务器上运行 Qwen3.5-9B 主实验矩阵。
- 保留 Qwen3.5-27B 早期探索和对照脚本。
- 提供 trace 生成、open-loop loadgen、duration loadgen、远程 runner、结果同步、summary、run state、dashboard 和 lifecycle replay。
- 支撑最终 12h 验收实验。

## 9B 最终矩阵

最终主线使用 Qwen3.5-9B，原因是它能在 2 x RTX 3090 上承载更多重复实验和更完整的 12h 矩阵。矩阵覆盖：

| Stage | 场景 | 主要验证点 |
| --- | --- | --- |
| High pressure throughput | 稳定共享前缀 + 容量压力 | prefix cache 质量、rebuilt-from-eviction、SLO goodput |
| Enterprise mixed traffic | 多 tenant、多 family、前台查询、后台任务、cold RAG | class latency、admission、foreground priority |
| Multi-turn long dialogue | session/turn 增长、共享主干和分叉 | family-protect、scheduler affinity、长上下文复用 |
| Low-reuse guard | 低复用、decode-heavy、冷流量 | 额外开销、尾延迟保护、非回归 |

所有 stage 使用同一套 KVFabric 代码和统一 controller，通过 stage-local preset 调整 admission、eviction、schedule 和 SLO protect 的强度。

## 27B 实验定位

Qwen3.5-27B 脚本和记录保留在 `long_pressure_benchmark/` 中，主要用于：

- 观察更高显存压力下的服务行为。
- 对比早期长压设计。
- 给 9B 矩阵提供 workload 和指标经验。

由于运行成本和稳定性约束，最终验收主线以 9B 矩阵为准。

## 推荐使用顺序

1. 用 `prebenchmark_validation/` 跑本地 smoke 和短 A/B。
2. 用 `benchmarks/lifecycle_policy/` 解释策略行为。
3. 用 `langtime_running_test/` 构造长对话和多轮分叉场景。
4. 用 `long_pressure_benchmark/` 跑远程 9B 中等实验和 12h 矩阵。
5. 用 `paper_reproductions/` 承接论文复现和横向比较。

## 结果保存约定

- 大量原始 `runs/` 默认不提交。
- 正式 run 需要保留 config、trace、run state、heartbeat、summary 和关键日志。
- 代表性结果整理成 `summary.md`、`ab_comparison.md`、dashboard 截图或 `docs/current/` 中的阶段文档。
- 每个结论应能追溯到具体 run、脚本和统计口径。
