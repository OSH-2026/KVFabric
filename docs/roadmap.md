# Roadmap

本文档记录 KVFabric 从选题、baseline、源码探针到策略原型验证的实际推进路线。当前项目主线是基于 vLLM Python 控制面的 KVCache 生命周期管理原型，而不是独立 runtime 或底层 kernel 改造。

## 时间范围

当前阶段覆盖 **2026-03-09** 到 **2026-06-08**。前半段用于方向收敛、vLLM baseline 和评测工具链搭建；后半段进入 vLLM 控制面探针、生命周期封装、共享感知策略和长对话/模板化 workload 验证。

## Milestones

### M0: 初步调研

- 时间：`2026-03-09` - `2026-03-16`
- 内容：
  - 调研 eBPF、协程调度器、KVCache 等方向。
  - 比较系统性、可落地性和展示空间。

### M1: 方向收敛

- 时间：`2026-03-16` - `2026-03-23`
- 内容：
  - 确定以 KVCache 为主线。
  - 继续调研 vLLM、llama.cpp 与 LLM serving 系统。

### M2: 主题细化

- 时间：`2026-03-23` - `2026-03-30`
- 内容：
  - 明确以 KVCache 生命周期管理、共享复用和驱逐策略为主要问题。
  - 将项目定位从单点性能优化调整为 LLM serving 中的 KVCache 资源管理。

### M3: 环境准备与早期验证

- 时间：`2026-03-30` - `2026-04-13`
- 内容：
  - 完成分工、资料整理和环境预备。
  - 为 vLLM 本地 bring-up 做前置准备。

### M4: vLLM 本地部署与 smoke test

- 时间：`2026-04-14` - `2026-04-27`
- 内容：
  - 在本地 Linux / WSL2 环境中部署官方 vLLM。
  - 跑通 offline inference 与 online serving。
  - 记录环境与最小可用验证结果。
  - 在仓库内沉淀可复用的 `vllm_baseline/` 工作区。

### M5: vLLM 代码路径梳理与基线测试

- 时间：`2026-04-28` - `2026-05-11`
- 内容：
  - 阅读 scheduler、prefix cache、block pool、KV cache manager 等关键路径。
  - 跑第一轮基础性能和 prefix caching 测试。
  - 形成 `experiments/prebenchmark_validation/` 和 `experiments/paper_reproductions/` 的评测入口。
  - 明确 vLLM 中适合接入生命周期观测与策略的 Python 控制面位置。

### M6: 生命周期设计与最小闭环

- 时间：`2026-05-12` - `2026-05-30`
- 内容：
  - 设计 KV block 生命周期状态、side table 字段、事件日志和指标口径。
  - 完成 `experiments/benchmarks/lifecycle_policy/` 纯 Python 最小闭环。
  - 用合成 workload 验证 LRU 与 shared-aware 思路的可解释差异。
  - 准备 vLLM overlay 工作流，保证源码改动可以 patch、应用和回退。

### M7: 探针、封装与 vLLM 控制面原型

- 时间：`2026-05-31` - `2026-06-06`
- 内容：
  - 初步完成 vLLM 控制面生命周期探针。
  - 新增 `kvfabric_lifecycle.py`，维护 block 级 side table 和 JSONL 事件流。
  - 在 `BlockPool`、`KVCacheManager` 等路径接入 prefix lookup、block sealed、touch、evict、rebuilt-from-eviction 等事件。
  - 初步接入 Prometheus 指标探针和 lifecycle summary 脚本。
  - 在无策略或 LRU 模式下验证原行为可保持。

### M8: 长对话压测、策略验证与阶段总结

- 时间：`2026-06-07` - `2026-06-08`
- 内容：
  - 完成长时间对话压测程序设计与实现。
  - 初步加入并验证 `shared_aware`、`family_protect`、admission control 等策略。
  - 构造普通无共享、模板 family 回访、多周期回访、cache pressure 等 workload。
  - 通过 A/B 对比验证：普通无共享场景低开销退化；模板化和相似多轮场景中，KVFabric 能减少共享主干误驱逐，提高 prefix-hit tokens，并带来小幅请求级收益。
  - 整理阶段文档、日志、报告和复跑交接说明。

## 当前收尾重点

当前阶段的重点不是继续扩大功能边界，而是把已有原型和实验结果整理成可信交付：

- 更新 README、overlay README、prebenchmark README 和 current docs，使其与实际实现一致。
- 补齐 `2026-05-31` 和 `2026-06-07` 两次小组讨论与实现日志。
- 复跑并保留少量代表性 A/B 结果。
- 明确当前尚未实现的内容：非严格 chunk 级共享、真实 CoW、显式 prefix-family tree、scheduler 改调度等均作为后续工作。
