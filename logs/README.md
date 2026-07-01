# KVFabric 开发日志索引

本目录记录 KVFabric 的小组讨论、阶段实现、远程实验和汇报节点。早期日志主要记录选题、调研、vLLM bring-up 和评测工具建设；中期日志记录 lifecycle 探针、策略原型和长时间对话压测；后期日志记录远程 9B/27B 实验平台、指标体系、批量实验、dashboard/replay 和期末汇报整理。

日志定位：

- 追踪每次讨论的背景、决策、分工和结果。
- 记录从问题发现到代码/工具改进的过程。
- 给 README、roadmap、期末报告和 PPT 提供可追溯依据。
- 避免实验结果只散落在临时 run 目录或单次脚本输出中。

## 日志索引

| 日期 | 阶段 | 主题 | 主要内容 | 相关产物 |
| --- | --- | --- | --- | --- |
| [2026-03-23](./2026-03-23.md) | 个人选题调研 | 候选方向启动 | 组内线上会议交流个人选题想法，讨论 eBPF、协程调度器、KV Cache、轻量 OS 等方向的可行性。 | 初步确定继续个人调研，准备下一轮选题收敛 |
| [2026-03-28](./2026-03-28.md) | 初组选题 | LoongArch OS 方向讨论与反馈 | 线下讨论初组选题并向老师汇报，原方向被认为风险与展示重点不够合适。 | 重新选题，转向 LLM serving / KV Cache 方向 |
| [2026-03-29](./2026-03-29.md) | 重新选题 | KV Cache 生命周期管理方向通过 | 周家润、赵天翔、王允分别完成新方向调研，组内决定采用 KV Cache 生命周期管理、共享复用和驱逐协同优化方向，并再次向老师汇报。 | [周家润调研](../docs/research/individual_research/ZhouJiarun/zjr_research.md)，[赵天翔调研](../docs/research/individual_research/ZhaoTianxiang/ztx_research2.md)，[王允调研](../docs/research/individual_research/WangYun/wy_research.md) |
| [2026-04-07](./2026-04-07.md) | 学习与平台选型 | LLM 推理、KV Cache 与 vLLM / llama.cpp 比较 | 学习 PagedAttention、prefix caching、KV block 管理和推理服务指标，比较 vLLM 与 llama.cpp 适配性。 | [小组研究报告](../docs/research/group_research/research_report.md)，[vLLM vs llama.cpp](../docs/research/group_research/vllm-vs-llamacpp.md) |
| [2026-04-14](./2026-04-14-vllm-bringup.md) | baseline 搭建 | vLLM bring-up | 搭建 vLLM 环境，跑通 offline inference、OpenAI-compatible serving 和最小 API 验证。 | [vLLM baseline](../vllm_baseline/README.md)，[可行性报告](../docs/reports/feasibility_report.md) |
| [2026-04-19](./2026-04-19.md) | 源码阅读准备 | vLLM 改造范围讨论 | 讨论 scheduler、prefix cache、KVCacheManager、BlockPool、metrics 等源码路径，明确优先改 Python 控制面。 | [architecture overview](../docs/architecture/overview.md) |
| [2026-04-23](./2026-04-23.md) | 评测建设 | 论文方法与 benchmark 复现分工 | 确定评测工具和论文复现方向，拆分 KVCache 质量评测、prefix cache 评测和 vLLM 性能评测任务。 | [任务拆分](./2026-04-23_work.md)，[vLLM performance benchmark](../experiments/paper_reproductions/vllm_performance_benchmark/README.md)，[KVCache quality benchmark](../experiments/paper_reproductions/kvcache_quality_benchmark/README.md) |
| [2026-04-28](./2026-04-28.md) | 中期准备 | 中期汇报前整理 | 检查 KVCache 指标评测方法和中期汇报内容，确定 PPT 与课堂提问分工。 | [中期 PPT](../docs/media/KVFabric_midterm_report.pptx) |
| [2026-05-06](./2026-05-06.md) | 中期汇报 | 老师建议与后续方向 | 课上汇报项目进展，记录老师关于 OS 式 inference memory management、workload model 和可解释评测的建议。 | [后续建议](./参考.md) |
| [2026-05-09](./2026-05-09.md) | 最小闭环 | lifecycle policy loop | 决定先完成纯 Python、确定性可复现的最小闭环，用于解释生命周期元数据、LRU 与 shared-aware 的区别。 | [lifecycle policy benchmark](../experiments/benchmarks/lifecycle_policy/README.md) |
| 2026-05-24 | 源码改造启动 | vLLM 探针与长对话压测准备 | 开始向 vLLM 源码加入 KV block 状态探针；同步准备长时间对话压测数据和脚本。 | [longtime running test](../experiments/langtime_running_test/README.md) |
| [2026-05-31](./2026-05-31.md) | 控制面探针 | lifecycle probe 与最小策略路径 | 初步完成 `kvfabric_lifecycle.py`，在 vLLM 控制面记录 prefix lookup、block sealed、touch、evict、rebuilt-from-eviction 等事件。 | [iteration log](../docs/current/kvfabric_iteration_log.md)，[vLLM overlay](../vllm_workspace/README.md) |
| [2026-06-07](./2026-06-07.md) | 策略原型 | 长对话 benchmark 与策略验证 | 完成长时间对话压测设计和实现，接入 `shared_aware`、`family_protect`、admission control，并完成普通、模板、多轮和 cache pressure A/B。 | [prebenchmark validation](../experiments/prebenchmark_validation/README.md) |
| [2026-06-15](./2026-06-15.md) | 远程实验准备 | 2 x RTX 3090 长测平台 | 讨论大规模实验平台，决定由周家润主要在服务器上操作，使用 Qwen3.5-9B 和 Qwen3.5-27B 重跑早期实验并开展远程长测。 | [long pressure benchmark](../experiments/long_pressure_benchmark/README.md) |
| [2026-06-22](./2026-06-22.md) | 指标与工具链 | 真实化 trace、open-loop loadgen、summary | 设计 e2e/class/segment/SLO 指标，构造 tenant/family/session/turn/phase trace，完成调试和评测工具链，支撑服务器连续实验和代码迭代。 | [9B 实验设计](../docs/current/kvfabric_qwen9b_experiment_design_2026-06-30.md) |
| [2026-06-29](./2026-06-29.md) | 批量实验与可视化 | dashboard、replay、最终矩阵 | 进行批量远程实验，修正 admission、scheduler、latency header 等问题，实现实时 dashboard/replay，设计最终 12h 实验矩阵。 | [6 月迭代历史](../docs/current/kvfabric_june_iteration_history_2026-06-30.md)，[dashboard/replay design](../docs/current/kvfabric_dashboard_replay_design_2026-06-28.md) |
| [2026-06-30_2026-07-01](./2026-06-30_2026-07-01.md) | 期末汇报 | 内容整理与分工 | 整理当前代码设计、后期迭代、调试工具、9B 实验设计和 12h 结果展示，完成期末汇报材料归档。 | [期末汇报 PPT](../docs/endterm/KVFabric期末汇报.pptx)，[最终代码设计](../docs/current/kvfabric_final_code_design_vs_vllm_2026-06-30.md) |

## 关键节点细化

| 时间 | 节点 | 背景问题 | 主要改进 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-03-23 ~ 2026-03-29 | 选题收敛 | 初始 OS 方向缺少稳定展示路径，KV Cache 方向更能体现资源管理和系统优化。 | 重新调研 LLM serving、KVCache 生命周期、prefix caching、共享复用和驱逐策略。 | 项目确定为面向 LLM serving 的 KV Cache 生命周期管理系统。 |
| 2026-04-07 ~ 2026-04-23 | 平台与评测准备 | 需要先跑通参考系统并建立可复用 benchmark，才能判断后续改造收益。 | 选择 vLLM 作为主平台，搭建 baseline，建立性能评测和质量评测目录。 | 完成 vLLM bring-up、平台选型和初步 benchmark 入口。 |
| 2026-05-06 ~ 2026-05-09 | OS 式问题定义 | 中期后需要把项目从“缓存技巧”提升到“推理内存管理”表述，并形成最小闭环。 | 明确 lifecycle side table、working set、admission、eviction regret 等 OS 类比；实现纯 Python 最小闭环。 | 项目有了可解释的策略模型和指标口径。 |
| 2026-05-24 ~ 2026-05-31 | vLLM 控制面接入 | 合成闭环不能代表真实 vLLM 行为，需要进入 BlockPool / KVCacheManager。 | 在 vLLM Python 控制面接入 lifecycle probe、JSONL 事件、side table 和 metrics。 | 能观察真实 KV block 从分配到驱逐的生命周期。 |
| 2026-06-07 | 策略原型验证 | 只有观测还不够，需要验证 shared-aware / family-protect 是否能改变 eviction quality。 | 增加策略开关和 A/B 配置，构造普通、模板、多轮和 cache pressure workload。 | 普通场景低干预，模板/多轮场景能减少共享主干误驱逐。 |
| 2026-06-15 | 远程长测启动 | 本地短测无法支撑 9B/27B 长周期结论，也无法覆盖真实压力和 SLO。 | 建立远程服务器实验计划，确定 2 x RTX 3090、Qwen3.5-9B/27B 和重跑对照流程。 | 项目从本地机制验证转向远程实验验证。 |
| 2026-06-15 ~ 2026-06-22 | 指标与 workload 重构 | raw tok/s 和平均 latency 无法解释 class 差异、排队延迟和 lifecycle 收益。 | 设计 e2e、class、segment、SLO goodput、rebuilt 和 lifecycle summary；构造真实化 trace 与 open-loop replay。 | 实验能解释“哪类请求变好、代价在哪、收益来自哪条路径”。 |
| 2026-06-22 ~ 2026-06-29 | 代码和架构迭代 | 远程实验暴露 admission churn、promotion fairness、header 丢失和 run state 不清等问题。 | 重构 admission 入口，修 header whitelist，引入 hit-aware scheduler、latency guard、run state、heartbeat、dashboard 和 replay。 | 形成统一 controller 和最终 12h 实验矩阵。 |
| 2026-06-30 ~ 2026-07-01 | 汇报材料整理 | 需要把工程实现、实验过程和结果转化为期末汇报材料。 | 整理代码设计、迭代问题、调试工具、实验设计、12h 结果和 PPT。 | 完成期末汇报材料归档，并将 README、日志和 roadmap 同步到最终状态。 |

## 阶段脉络

### 1. 选题与问题定义

3 月下旬的日志记录了从多个 OS 课程项目候选方向到 KV Cache 生命周期管理方向的收敛过程。这个阶段的关键点是确认项目具有明确的系统属性：KV block 可以类比物理页，prefix cache 可以类比共享页，驱逐与重建可以类比 page replacement 和 fault/reload，admission 和 scheduler 可以类比工作集保护与资源调度。

### 2. vLLM baseline 与评测基础

4 月的日志记录了 vLLM 环境搭建、源码阅读和 benchmark 目录建设。该阶段形成了三个基础：

- `vllm_baseline/`：负责官方 vLLM 运行、模型 profile、server 启停和 API 验证。
- `experiments/paper_reproductions/`：负责性能/质量评测复现入口。
- `docs/research/` 与 `docs/reports/`：保留平台选择、问题定义和可行性论证。

### 3. lifecycle 最小闭环与 vLLM 控制面接入

5 月下旬至 6 月 7 日的日志记录了项目从合成闭环进入真实 vLLM 控制面的过程。这个阶段完成：

- `kvfabric_lifecycle.py` side table。
- JSONL lifecycle event logger。
- Prometheus metrics probe。
- `shared_aware` retain-score eviction。
- `family_protect` 共享主干保护。
- admission control 早期版本。
- 长时间对话、多轮分叉和 cache pressure workload。

### 4. 远程长测平台建设

6 月 15 日以后，项目重心转向远程服务器实验。周家润主要负责在 2 x RTX 3090 服务器上部署、运行和同步结果，模型选择包括 Qwen3.5-9B 与 Qwen3.5-27B。这个阶段重点解决：

- 本地短测结论无法支撑长周期 A/B 对比。
- 部署、启动、trace replay、结果同步、summary 生成需要串成闭环。
- 早期实验需要在远程环境重跑，形成后续策略迭代可对比的 baseline。
- 长测需要 run state、heartbeat 和日志归档，避免 partial run 被误判为完成。

### 5. 指标、请求和工具链迭代

6 月 15 日至 6 月 22 日，实验设计从人工 hot/cold workload 扩展为更贴近服务形态的 trace：

- 使用 tenant、family、session、turn、phase 描述企业知识库、多轮对话、冷启动和低复用请求。
- 使用 request class 区分 foreground、background、durable、session、cold RAG、decode-heavy 和 low-reuse。
- 使用 `scheduled_at_seconds` 做 open-loop replay，降低 A/B 实验的 workload drift。
- 增加 e2e latency、class latency、segment throughput、SLO goodput、rebuilt-from-eviction 和 lifecycle summary。
- 增加远程 runner、summary、日志归档和错误诊断工具，支撑服务器上的连续代码迭代。

### 6. 批量实验、dashboard 与最终矩阵

6 月 22 日至 6 月 29 日，围绕远程实验暴露的问题继续修改代码和实验工具：

- 修正 admission limit 与 block hash 一致性问题。
- 修复 SLO、session、turn 等 header 在 OpenAI serving 路径中的传递问题。
- 将 scheduler promotion 从简单优先级改为带 class、hint、age 和 defer guard 的评分选择。
- 引入 run state、heartbeat、rolling metrics、dashboard 和 replay，避免 partial 或 stalled run 被误认为完成。
- 设计最终 12h 实验矩阵，作为主要验收结果。

### 7. 汇报材料整理

6 月 30 日和 7 月 1 日，项目进入期末汇报准备阶段。主要工作包括：

- 梳理当前代码设计及其相对 vLLM 的改动。
- 整理 6 月中下旬的主要问题和对应改进。
- 说明 Qwen3.5-9B 各类实验的请求组成、发送方式和验证目标。
- 从完整 12h 实验中筛选可解释、可复查的结果，用于最终展示。

## 与 README / roadmap 的关系

- 主 README 记录项目整体状态、成员、阶段进展、实现入口和实验入口。
- `docs/roadmap.md` 记录从 3 月到 7 月 1 日的 milestone。
- `docs/current/kvfabric_iteration_log.md` 记录代码迭代细节。
- `docs/current/kvfabric_june_iteration_history_2026-06-30.md` 记录 6 月中下旬由远程实验驱动的架构和代码修改。
- 本目录日志用于按日期追溯每个阶段为什么做、谁负责、做了什么、产生了哪些文档和结果。
