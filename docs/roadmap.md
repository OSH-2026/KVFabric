# Roadmap

本文档记录 KVFabric 从选题、baseline、源码探针到远程长周期实验的实际推进路线。当前项目主线是基于 vLLM 0.22.1 Python 控制面的 KVCache 生命周期管理原型。

## 时间范围

当前阶段覆盖 **2026-03-09** 到 **2026-07-01**。前半段用于方向收敛、vLLM baseline 和评测工具链搭建；中段完成生命周期探针、共享感知策略和长对话 workload；后半段完成远程 9B 长周期实验、调试工具、实时可视化和最终 12h 矩阵。

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
  - 将项目定位为 LLM serving 中的 KVCache 资源管理。

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
  - 通过 A/B 对比验证普通无共享场景的低开销、模板化和相似多轮场景中的共享主干保护，以及 prefix-hit tokens 的改善。
  - 整理阶段文档、日志、报告和复跑交接说明。

### M9: 远程大规模实验准备

- 时间：`2026-06-15`
- 内容：
  - 讨论大规模实验和实验平台。
  - 确定在 2 x RTX 3090 服务器上开展远程实验，由周家润主要进行部署、运行和结果同步。
  - 使用 Qwen3.5-9B 作为主要长测模型，保留 Qwen3.5-27B 的探索和对照价值。
  - 计划重跑早期 A/B 和长对话实验，为后续策略迭代提供 baseline。

### M10: 指标、请求模型与工具链迭代

- 时间：`2026-06-15` - `2026-06-22`
- 内容：
  - 设计更合理的评测指标，包括 e2e latency、class latency、segment throughput、SLO goodput、rebuilt-from-eviction 和 lifecycle summary。
  - 用 tenant、family、session、turn、phase 和 request class 构造更接近真实服务的 trace。
  - 使用 `scheduled_at_seconds` 实现 open-loop replay，降低 A/B 实验中的 workload drift。
  - 完成远程 runner、结果同步、summary、duration loadgen、trace loadgen 和调试脚本。
  - 周家润在服务器上持续运行实验，根据结果推动代码迭代。

### M11: 批量实验、dashboard 与最终 12h 矩阵

- 时间：`2026-06-22` - `2026-06-29`
- 内容：
  - 进行批量远程实验并取得可解释的结果。
  - 修正 admission 进入位置、block hash 一致性、header whitelist、scheduler promotion 和 latency guard 等问题。
  - 实现 run state、heartbeat、rolling class metrics、实时 dashboard 和 lifecycle replay。
  - 设计最终完整 12h 实验矩阵，覆盖高压吞吐、企业混合流量、多轮长对话和低复用保护。
  - 将 Admission、Eviction、Schedule 和 SLO protect 收敛为统一 controller 参数。

### M12: 期末汇报材料整理

- 时间：`2026-06-30` - `2026-07-01`
- 内容：
  - 讨论期末汇报内容和分工。
  - 整理当前代码设计、相对 vLLM 的改进、接手后的迭代过程、调试工具、9B 实验设计和主要结果。
  - 将 12h 实验结果、summary、dashboard 截图和 lifecycle replay 素材整理为可汇报材料。
  - 更新 README、日志和 current docs，使项目入口文档与最终状态一致。

## 当前收尾重点

当前阶段重点是保证代码、实验和文档之间能够相互追溯：

- README、overlay README、experiment README 和 current docs 需要反映 9B 主矩阵和远程工具链的真实状态。
- 长测结果需要保留 run config、trace、run state、heartbeat、summary 和关键日志。
- 报告结论需要能追溯到具体实验、统计口径和代码路径。
- 未完成内容应清楚标注：token 级 trie、真实 CoW、跨请求物理 block 去重和更深层 scheduler 改造仍属于后续工作。
