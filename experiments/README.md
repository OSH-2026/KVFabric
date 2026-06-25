# Experiments

`experiments/` 统一管理 KVFabric 的实验资产。当前结构覆盖 baseline 预验证、真实 vLLM A/B、纯 Python 生命周期策略闭环、长时间对话压测、远程 27B 长压，以及论文复现/质量评测入口。

## 目录结构

```text
experiments/
├─ prebenchmark_validation/        # 早期 smoke、短验证和历史 run
├─ long_pressure_benchmark/        # 当前远程 27B 长周期压力测试
├─ benchmarks/
│  └─ lifecycle_policy/            # 纯 Python 生命周期策略最小闭环
├─ langtime_running_test/          # 长时间对话、多轮分叉和压力测试
└─ paper_reproductions/            # 性能/质量评测复现与扩展
```

## 当前入口

- `prebenchmark_validation/`
  早期真实 vLLM 验证套件。覆盖 offline/online 请求、prefix reuse、cache pressure、KVFabric lifecycle JSONL、Prometheus metrics 和 LRU vs family-protect A/B。新增长压不再放到这里。

- `long_pressure_benchmark/`
  当前远程 27B 长周期测试入口。正式方案包括 `saturation_throughput_12h`、`enterprise_mixed_trace_12h` 和 `sticky_conversation_trace_12h`。

- `benchmarks/lifecycle_policy/`
  纯 Python 合成闭环。用于解释 lifecycle side table、LRU vs shared-aware、eviction regret 和 TTFT/吞吐代理，不直接宣称真实 GPU 性能收益。

- `langtime_running_test/`
  长时间对话压测程序。覆盖 continuous、random topic、persona rotation、dataset driven、pressure test、multi-turn fork 等模式。

- `paper_reproductions/`
  保留 vLLM 标准性能评测、KVCache 质量评测和后续横向比较入口。

## 推荐使用顺序

1. 用 `prebenchmark_validation/` 跑真实 vLLM 小规模 A/B。
2. 用 `benchmarks/lifecycle_policy/` 解释策略思想和指标。
3. 用 `langtime_running_test/` 构造长对话、多轮和分叉型 workload。
4. 用 `long_pressure_benchmark/` 跑远程 27B 长周期压力测试。
5. 用 `paper_reproductions/` 承接正式性能/质量评测扩展。

## 结果保存约定

- 大量原始 `runs/` 默认不提交。
- 代表性结果可整理成 `summary.md`、`ab_comparison.md` 或 docs/current 中的阶段报告。
- 每个正式结论应保留 config、env、metrics 和对比脚本入口，保证可复现。
