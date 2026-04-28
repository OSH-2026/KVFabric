# KVCache Quality Benchmark Method

本方法文档对应 `/work` 中的“3. KVCache 压缩与质量评测”要求。

## 目标

围绕以下四个问题组织评测：

1. KVCache 优化后模型输出是否变差
2. 哪些任务最容易暴露质量下降
3. 压缩率、显存节省、吞吐提升和准确率下降之间怎么比较
4. KVFabric 当前阶段是否需要纳入这类质量评测

## 当前实现策略

当前仓库里还没有真实的 KV 压缩或量化实现，因此本目录先复现的是“质量评测框架”本身，而不是某一篇论文的 artifact。

也就是说，先把下面这些能力做成稳定入口：

- 统一任务集
- 统一 variant 接口
- 统一输出目录
- 统一逐题评分
- 统一跨 variant 汇总

当后续接入真实 candidate 方案时，这套流程可以直接复用。

## 任务覆盖

当前任务集包含四类：

1. 长上下文问答
2. 多轮对话记忆
3. 代码生成
4. 推理 / 算题

它们分别对应 `/work` 中提到的：

- 长上下文问答
- 多轮对话
- 代码生成
- 推理任务

## 当前指标

### 质量指标

- `overall_avg_score`
  全部任务的平均分，范围 `[0, 1]`

- `overall_pass_rate`
  全部任务的通过率，范围 `[0, 1]`

- `category_summary`
  按任务类别汇总的平均分与通过率

### 性能指标

- `load_seconds`
- `inference_seconds`
- `output_tokens_per_second`
- 粗粒度 CUDA 显存占用变化估计

### 当前未直接纳入的指标

- 真正的压缩率
- 真正的显存节省
- 真正的 kernel 级访存变化

这些指标需要在后续接入实际 KV 压缩/量化实现后，才能做严肃对比。

## variant 组织方式

每个候选方案由 `variants/*.env` 描述，至少包含：

- `SUITE_VARIANT_NAME`
- `VARIANT_PRESET`
- `VARIANT_DESCRIPTION`

必要时可加入：

- `OVERRIDE_MAX_MODEL_LEN`
- `OVERRIDE_GPU_MEMORY_UTILIZATION`
- `OVERRIDE_MAX_NUM_SEQS`
- `OVERRIDE_ENABLE_PREFIX_CACHING`

## 输出说明

每个 variant 输出一份独立运行目录，suite 级目录额外生成：

- `suite_summary.json`
- `suite_summary.md`

这样可以同时支持：

- 单 variant 回归
- baseline vs candidate 对比
- 多 candidate 横向比较

## 当前阶段建议

对于 KVFabric 当前阶段，更合理的结论不是“马上做完整质量 benchmark”，而是：

1. 先把质量评测框架搭好。
2. 先保留一组轻量、可解释、低成本的任务。
3. 真正有了 KV 压缩/量化实现后，再扩大任务集和对比矩阵。

因此，本目录更像“质量评测基础设施的第一版”，而不是最终实验结论本身。
