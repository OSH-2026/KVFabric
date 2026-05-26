# 生命周期策略基准

本目录是 KVFabric 当前的最小闭环：

```text
合成负载 -> 生命周期 side table -> 驱逐策略 -> 指标/报告
```

它刻意保持为纯 Python、确定性可复现的实验。目标是在把策略下沉到
vLLM 之前，先验证控制面里的生命周期建模、共享感知驱逐和指标链路。

## 覆盖内容

- 负载：完全共享前缀、模板分叉、RAG 长上下文、缓存压力。
- 元数据：命中次数、共享度、分叉度、前缀深度、重算代价。
- 策略：近似 LRU 与 `shared_aware` KVFabric 评分策略。
- 指标：命中率、节省的 prefill tokens、重算 tokens、驱逐后悔率、
  TTFT/TPOT 代理值、缓存压力、策略决策开销。

## 运行方式

从仓库根目录运行：

```bash
bash experiments/benchmarks/lifecycle_policy/scripts/run_minimal_closed_loop.sh
```

输出写入 `experiments/benchmarks/lifecycle_policy/runs/`：

- `metrics.json`：结构化的汇总指标与分负载指标。
- `eviction_events.jsonl`：逐条驱逐生命周期事件。
- `summary.md`：便于项目讨论的人类可读报告。

## 注

该基准不宣称真实 GPU 性能提升。它证明当前项目已经实现闭环：负载生成器、生命周期元数据、共享感知驱逐、与 LRU 的对比。
