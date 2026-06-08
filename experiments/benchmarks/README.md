# Benchmarks

本目录管理 KVFabric 的 benchmark 型实验。当前已有稳定入口是 `lifecycle_policy/`，用于纯 Python 生命周期策略最小闭环。

## 当前入口

### `lifecycle_policy/`

确定性合成 benchmark：

```text
合成负载 -> 生命周期 side table -> LRU / shared-aware 策略 -> 指标与报告
```

覆盖：

- 共享前缀；
- 模板分叉；
- RAG 长上下文；
- cache pressure；
- LRU 与 shared-aware 对比；
- hit rate、saved prefill tokens、recompute、eviction regret、TTFT/TPOT proxy。

运行：

```bash
bash experiments/benchmarks/lifecycle_policy/scripts/run_minimal_closed_loop.sh
```

该 benchmark 用于解释策略思想和指标口径，不替代真实 vLLM serving A/B。真实 vLLM 对比请使用：

```text
experiments/prebenchmark_validation/
```

## 后续可扩展方向

如果后续需要更正式的 benchmark 矩阵，可以新增：

```text
benchmarks/
├─ prefix_on_off_ab/
├─ lifecycle_eviction_ab/
├─ long_dialogue_ab/
└─ prototype_comparison/
```

当前收尾阶段优先保证已有 `lifecycle_policy/` 和 `prebenchmark_validation/` 的结果可信，而不是继续扩展大量新 benchmark。
