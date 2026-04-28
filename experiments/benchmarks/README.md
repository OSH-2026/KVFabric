# Benchmarks

本目录预留给正式 benchmark。

建议后续在这里放：

- 基线吞吐 / 延迟矩阵
- 改造前后 A/B 对比
- 多模型、多上下文长度、多并发配置的批量脚本
- 汇总图表、结果摘要与对应原始输出

如果某套 benchmark 已经形成稳定流程，建议继续按子目录拆分，例如：

```text
benchmarks/
├─ baseline_matrix/
├─ prefix_on_off_ab/
└─ prototype_comparison/
```
