# KVFabric

KVFabric 是一个面向大模型推理服务的 KV Cache 生命周期管理系统。项目基于 vLLM 0.22.1，在不重写推理引擎主体的前提下，为 KV block 增加生命周期状态、共享前缀关系、重算代价、保留价值、请求提示和调度反馈等控制面信息，并围绕这些信息实现可观测、可解释、可调节的缓存管理策略。

项目目标来自操作系统课程设计：把页生命周期、工作集、准入控制、置换策略和调度反馈等思想迁移到模型原生推理服务中，验证 KV Cache 是否可以从“被动缓存页”提升为“可管理资源对象”。

[English README](README_en.md) | [Architecture](docs/architecture/overview.md) | [Current Iteration Log](docs/current/kvfabric_iteration_log.md) | [vLLM Overlay](vllm_workspace/README.md) | [Long Pressure Benchmark](experiments/long_pressure_benchmark/README.md) | [Endterm PPT](docs/endterm/KVFabric期末汇报.pptx)

## 项目成员

- [周家润](https://github.com/QY-dream)
- [赵天翔](https://github.com/ZTX1115)
- [王允](https://github.com/mjswyy)

## 当前状态

截至 2026-07-01，项目已经完成从本地功能验证到远程长周期实验的闭环：

- 基于 vLLM 0.22.1 接入 KVFabric overlay，覆盖 BlockPool、KVCacheManager、Scheduler、OpenAI serving、metrics 和实验工具链。
- 实现 lifecycle side table、Prefix Family 元数据、evicted shadow、rebuilt-from-eviction 反馈、Prometheus 指标和 JSONL 事件流。
- 实现 shared-aware 驱逐、family-protect 共享主干保护、hint-aware admission、scheduler affinity、latency guard、SLO goodput 统计和 unified controller 参数化调节。
- 建立本地 Qwen3.5-2B smoke test、远程 2 x RTX 3090 上 Qwen3.5-9B 长周期实验、早期 Qwen3.5-27B 探索和回归对比流程。
- 完成 deploy / run / sync / summary / dashboard / replay 工具链，支持长测复现、失败诊断、生命周期回放和结果归档。
- 形成最终 12h 实验矩阵，覆盖高压吞吐、企业混合流量、多轮长对话、低复用保护和容量敏感性等场景。

实验结果表明，在高压、稳定共享前缀和冷热混合流量中，KVFabric 可以减少错误驱逐后的重建，提升 prefix cache 使用质量，并在 SLO 边界场景下提高 goodput；在普通低频混合流量和低复用场景中，额外开销可控，没有观察到明显退化。

阶段性结论按 workload 分类理解：

- 普通无共享请求：KVFabric 基本退化为低干预路径，重点观察 overhead 和非回归。
- 模板化 prompt、企业固定工作流和多轮对话：共享前缀具有长期复用价值，适合观察 eviction quality、prefix-hit tokens 和 rebuilt-from-eviction。
- 高压冷热混合流量：短期 cold / burst 请求会挤压高价值共享主干，适合验证 admission、family-protect 和 shared-aware eviction。
- SLO 边界场景：raw tok/s 之外，更关注满足 SLO 的 goodput、foreground latency 和 class-level latency。
- 低复用与 decode-heavy 场景：用于检查策略边界，确认 scheduler promotion 和 admission 不会破坏公平性与尾延迟。

## 目录结构

```text
KVFabric/
├── vllm_workspace/                 # vLLM 0.22.1 工作区与 KVFabric overlay
├── vllm_baseline/                  # 原始 vLLM / baseline 对照环境
├── experiments/
│   ├── long_pressure_benchmark/    # 远程长周期压测、trace 生成、summary、dashboard
│   ├── benchmarks/                 # lifecycle policy 与早期策略实验
│   ├── prebenchmark_validation/    # 本地预验证
│   └── paper_reproductions/        # 论文复现实验
├── docs/
│   ├── architecture/               # 架构设计说明
│   ├── current/                    # 当前阶段设计、实验和迭代文档
│   ├── baseline/                   # vLLM baseline 阅读记录
│   └── reports/                    # 阶段性报告
├── logs/                           # 按日期整理的开发日志
└── scripts/                        # 部署、环境和辅助脚本
```

## 关键机制

| 模块 | 作用 |
| --- | --- |
| Lifecycle side table | 为每个 KV block 记录状态、hash、深度、命中、共享、重算代价、保留分数和最近访问时间 |
| Prefix Family | 按 root / parent / family 维护共享前缀主干与分叉关系，为共享保护和统计提供依据 |
| Evicted shadow | 记录已驱逐 block 的摘要信息，用于识别后续 rebuilt-from-eviction |
| Shared-aware eviction | 在 eviction 分数中加入共享程度、命中历史、深度和重建反馈，降低热共享前缀被驱逐的概率 |
| Family-protect | 对稳定共享家族的浅层主干设置保护深度，避免高价值 prefix 被短期冷流量冲掉 |
| Hint-aware admission | 根据请求类型、durable/session hint、prefix 命中情况和容量压力决定缓存写入范围 |
| Scheduler affinity | 在 waiting queue 中识别高 prefix 命中请求，通过有界 promotion 把缓存收益转成调度收益 |
| Latency guard | 对前台、decode-heavy、低复用和长输出请求设置 age/defer 上限，控制 promotion 对尾延迟的影响 |
| Metrics / JSONL / dashboard | 输出 lifecycle、class、segment、SLO、rebuilt 和 run state 数据，支撑调试、验收和可视化 |

## 项目方向

KVFabric 当前的项目方向是围绕 vLLM 中 KV Cache 的生命周期管理做一个可运行、可观测、可解释、可对照的系统原型。系统持续记录 KV block 从创建、写满、进入 prefix cache、被共享、引用归零、进入候选、被驱逐到后续重建的过程，并把这些信息用于共享感知驱逐、admission 和 scheduler 实验。

当前实现主要落在 vLLM Python 控制面：

- `vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py`：维护 lifecycle side table、JSONL 事件日志、retain score、evicted shadow、family-protect 选择器和 admission 状态。
- `vllm_workspace/overlay/vllm/v1/core/kvfabric_family.py`：维护 prefix family 的 root、parent、branch、protected depth 和 family-level 统计。
- `vllm_workspace/overlay/vllm/v1/core/kvfabric_hints.py`：解析 request class、cache priority、expected reuse、tenant、family、session、turn 和 SLO hint。
- `vllm_workspace/overlay/vllm/v1/core/block_pool.py`：接入 block sealed、touch、free、evict 和候选选择逻辑。
- `vllm_workspace/overlay/vllm/v1/core/single_type_kv_cache_manager.py`：承载 admission limit 的实际入口，避免多处限制造成 block hash 不一致。
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py`：记录 request 级 prefix lookup、prompt tokens 和 hit tokens。
- `vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py`：接入 waiting queue scan、`peek_computed_tokens()`、promotion scoring、age guard、defer cap 和 latency-protected class。
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py` 与 `vllm_workspace/overlay/vllm/v1/metrics/`：导出 block lookup、eviction、rebuilt、metadata overhead、waiting queue、class latency 和 SLO goodput 指标。

策略方向分为四层：

- 生命周期封装：把 KV block 的状态和共享关系写入 side table，使后续实验能解释每一次命中、释放、冷却和驱逐。
- 共享主干保护：通过 `hit_count`、`share_degree`、`branch_factor`、`prefix_depth`、family hit 和 protected depth 等信号识别长期可复用的 prefix family。
- 准入与置换联动：在 cache 写入阶段减少 cold / low-reuse churn，在 eviction 阶段减少高价值共享前缀被短期流量冲掉。
- 调度与评测联动：用 scheduler affinity 和 latency guard 把 prefix cache 质量转化为请求级收益，再用 class metrics、SLO goodput 和 lifecycle JSONL 解释收益来源。

## 核心设计展开

### 生命周期封装

KVFabric 在 vLLM 控制面维护 lifecycle side table，把每个 KV block 的运行状态转化为可观测对象。当前记录的核心字段包括：

- block id 与 block hash；
- prefix depth 与 recompute cost proxy；
- ref count、hit count、share degree、branch factor；
- 生命周期状态：free、active、sealed、shared、cooling、evicted 等；
- family id、root hash、parent hash、protected depth；
- 驱逐时 retain score、evict time 和后续 rebuilt-from-eviction 标记。

这些字段不改变 worker 侧 block table 或 attention kernel 语义，主要用于观测、策略选择和实验解释。当前实现记录 block 级和 family 级近似共享信号，没有实现 token 级 trie、完整 child branch 权重分布或跨请求物理 block 去重。

### 共享主干与私有尾部

在 vLLM 的严格 prefix caching 语义下，多个请求可能共享完整 full-block 前缀，之后追加不同的私有尾部。KVFabric 将这类结构抽象为 prefix family：

- 共享主干 block：通常位于 prompt 前段，可能被系统 prompt、企业文档、RAG 模板、多轮历史反复复用，应优先保护。
- 分叉 block：位于 family 后续分叉位置，代表不同 session、turn 或 request class 的差异。
- 私有尾部 block：通常属于单个请求的后缀，长期复用概率低，更适合作为驱逐候选。
- 分叉代理指标：通过 `share_degree`、`hit_count`、`branch_factor`、`prefix_depth` 和 family-level counter 近似描述共享结构价值。

### 准入控制

KVFabric 的 admission 逻辑用于决定哪些请求和哪些深度的 block 进入 prefix cache。6 月下旬后，admission limit 收敛到 `SingleTypeKVCacheManager.cache_blocks()` 这一条路径：

- durable hot family 和 session 请求保留完整缓存机会；
- cold RAG、burst、low-reuse 和 decode-heavy 请求在容量紧张时限制缓存深度；
- admission saved blocks 写入 summary，用于解释减少 churn 的收益；
- 避免在多个位置重复限制缓存，防止 block hash、cached blocks 和 side table 状态不一致。

### 驱逐策略

当前 overlay 中保留两类主要策略：

- `shared_aware`：基于 retain score 对候选 block 做排序，优先驱逐低保留价值 block。
- `family_protect`：轻量保护长期复用 family。它保持 vLLM free queue 的原始顺序，只在候选中遇到 protected block 时延后驱逐，降低无压力场景的排序开销。

retain score 主要考虑命中历史、共享程度、prefix depth、recompute cost、branch factor 和 rebuilt-from-eviction 反馈。策略开关由环境变量或 controller preset 控制，默认可退回 vLLM 原行为。

### 调度反馈

远程实验显示，保护 cache block 之后，还需要让高复用请求及时被调度，否则缓存质量无法转成端到端收益。当前 scheduler 侧加入：

- waiting queue scan；
- `peek_computed_tokens()` 前缀命中估计；
- foreground / durable / session 请求 promotion；
- age guard 和 defer cap；
- decode-heavy、低复用和长输出请求的 latency protection；
- class/hint/queue pressure 共同参与的 scoring。

最终口径收敛为有界 foreground-priority：热 prefix 和前台交互请求可以获得调度亲和性，同时对低复用和长输出请求设置上限保护。

### 事件日志与指标

KVFabric 当前支持三条观测链路：

- JSONL lifecycle events：用于实验后处理、debug 和 replay。
- Prometheus metrics：用于请求级、block 级、队列级指标汇总。
- Summary / dashboard / replay：用于长测验收、实时诊断和汇报展示。

关键事件包括：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `request_hints_observed`
- `request_deferred`
- `eviction_candidates_ranked`
- `block_evicted`
- `lifecycle_reset`

关键指标包括：

- prefix hit rate / prefix-hit tokens；
- evicted blocks、protected evictions、admission saved blocks；
- rebuilt-from-eviction blocks 和 rebuild gap；
- shared-anchor eviction ratio 与 family-level hit；
- TTFT、TPOT、E2E latency、class latency；
- requests/s、prompt tok/s、completion tok/s；
- SLO goodput、segment goodput、SLO probe；
- metadata update overhead、block lookup overhead、waiting queue size 和 waiting time。

## 项目阶段进展

| 项目阶段 | 日期 | 项目进展 | 具体分工 | 完成情况 | 附录 |
| --- | --- | --- | --- | --- | --- |
| 个人选题调研 | 2026-03-23 | 组内线上会议，交流个人选题想法，讨论 eBPF、协程调度器、KV Cache、轻量 OS 等多个方向。 | 三位成员分别整理候选方向，比较系统性、可落地性、展示空间和课程匹配度。 | 决定会后继续个人调研，并在下一轮组内会议中汇总，形成初步选题方向。 | [log](logs/2026-03-23.md) |
| 初组选题 | 2026-03-28 | 线下会议交流选题想法，初步倾向在 LoongArch 开发板上实现可运行验证性操作系统。 | 周家润提出基于 eBPF 的 KV Cache 性能剖析方向；赵天翔提出面向 LoongArch 自研 CPU 的应用承载型 OS；王允提出 Rust 改写简单 OS。 | 小组先决定采用 LoongArch 验证性 OS 方向，并准备向老师汇报。 | [log](logs/2026-03-28.md)，[赵天翔调研](docs/research/individual_research/ZhaoTianxiang/ztx_research1.md) |
| 选题反馈 | 2026-03-28 | 线上向老师报告初组选题并咨询意见。 | 小组共同汇报选题动机、硬件基础和课程实现边界。 | 老师认为原方向风险和展示重点不够合适，需要重新收敛题目。 | [log](logs/2026-03-28.md) |
| 重新调研与选题收敛 | 2026-03-29 | 组员分别完成新一轮调研，并召开线上会议讨论 LLM serving 与 KV Cache 管理方向。 | 周家润调研 KV Cache 生命周期、chunk 级复用和 CoW 分叉；赵天翔调研 KVCache 分配、复用与驱逐协同优化；王允调研移动端轻量 AI 用户态调度引擎。 | 决定采用“KV Cache 统一生命周期管理 + 共享复用 + 驱逐协同优化”的方向。 | [log](logs/2026-03-29.md)，[周家润调研](docs/research/individual_research/ZhouJiarun/zjr_research.md)，[赵天翔调研](docs/research/individual_research/ZhaoTianxiang/ztx_research2.md)，[王允调研](docs/research/individual_research/WangYun/wy_research.md) |
| 选题确认 | 2026-03-29 | 再次向老师汇报 KV Cache 方向。 | 小组说明该方向与操作系统资源管理、缓存生命周期、共享关系和驱逐策略之间的对应关系。 | 选题通过，后续围绕 vLLM / llama.cpp 等推理框架继续调研。 | [log](logs/2026-03-29.md) |
| 学习与平台选型 | 2026-04-07 | 学习 LLM 推理、KV Cache、prefix caching、PagedAttention 和推理服务调度机制，比较 vLLM 与 llama.cpp。 | 周家润整理 KVFabric 小组研究报告；赵天翔比较 vLLM 与 llama.cpp 的系统适配性；王允整理平台优缺点和测试入口。 | 完成初步学习，决定以 vLLM 作为主要实现平台，llama.cpp 作为对照和轻量验证材料。 | [log](logs/2026-04-07.md)，[小组研究报告](docs/research/group_research/research_report.md)，[vLLM vs llama.cpp](docs/research/group_research/vllm-vs-llamacpp.md) |
| vLLM baseline 搭建 | 2026-04-13 ~ 2026-04-14 | 搭建 vLLM 基线环境，打通 offline inference、OpenAI-compatible serving 和基础 metrics 读取。 | 周家润负责环境搭建、模型下载、推理链路和性能数据收集；赵天翔撰写可行性报告；王允整理日志和文档。 | 成功搭建 vLLM 环境，完成端到端推理链路验证，沉淀 `vllm_baseline/` 工作区。 | [log](logs/2026-04-14-vllm-bringup.md)，[baseline README](vllm_baseline/README.md)，[可行性报告](docs/reports/feasibility_report.md) |
| 改造范围讨论 | 2026-04-19 | 线下会议讨论后续 vLLM 改造范围、源码阅读顺序和模块边界。 | 小组围绕 scheduler、prefix cache、KVCacheManager、BlockPool、metrics 等路径分工阅读。 | 确定优先读清 vLLM Python 控制面，后续先在控制面接入 lifecycle 元数据和策略，不优先改 CUDA kernel。 | [log](logs/2026-04-19.md) |
| 评测方法与论文复现 | 2026-04-23 | 线下会议确定后续任务：阅读前沿论文，复现 vLLM 与 KVCache 性能评测方法，准备可复用 benchmark。 | 周家润负责 KVCache 压缩与质量评测流程；赵天翔负责 KVCache 复用与前缀缓存评测；王允负责 vLLM 标准基础服务性能评测。 | 形成 `paper_reproductions/`、性能评测和质量评测入口，为后续对照实验提供基础。 | [log](logs/2026-04-23.md)，[任务拆分](logs/2026-04-23_work.md)，[vLLM performance benchmark](experiments/paper_reproductions/vllm_performance_benchmark/README.md) |
| 中期汇报准备 | 2026-04-28 | 线下会议检查 KVCache 指标评测方法和中期汇报材料。 | 周家润负责中期汇报 PPT 设计与制作；赵天翔和王允负责了解其他组项目并准备提问。 | 完成中期汇报材料准备。 | [log](logs/2026-04-28.md)，[中期 PPT](docs/media/KVFabric_midterm_report.pptx) |
| 中期汇报 | 2026-05-06 | 课上汇报当前项目进展，回答老师和同学问题。 | 周家润、赵天翔负责汇报与回答问题；王允负责记录问题、建议和后续修改方向。 | 老师建议将项目表述为 inference memory management，突出 OS 式资源管理而非普通缓存技巧。 | [log](logs/2026-05-06.md)，[后续建议](logs/参考.md) |
| 最小闭环设计 | 2026-05-09 | 线下会议讨论后续规划，决定先做纯 Python、确定性可复现的 lifecycle policy 最小闭环。 | 赵天翔负责 lifecycle policy loop；周家润、王允配合确定 workload、指标和解释口径。 | 完成最小闭环方向设计，后续用于解释 LRU、shared-aware、eviction regret 和 TTFT/吞吐代理。 | [log](logs/2026-05-09.md)，[lifecycle policy benchmark](experiments/benchmarks/lifecycle_policy/README.md) |
| vLLM 源码改造启动 | 2026-05-24 | 线下会议讨论 vLLM 源码改造，开始向真实控制面接入探针。 | 赵天翔向 vLLM 源码中加入 KV block 状态探针；周家润实现数据封装和 summary；王允准备长时间测试所需数据集与对话压测入口。 | 明确 lifecycle side table、事件日志和长时间对话压测三条并行工作线。 | [长时间对话压测](experiments/langtime_running_test/README.md) |
| lifecycle 探针与封装 | 2026-05-31 | 初步完成 vLLM 控制面 lifecycle 探针和封装。 | 赵天翔完善 `kvfabric_lifecycle.py`，在 `BlockPool`、`KVCacheManager` 中接入 prefix lookup、block sealed、touch、evict 等事件；周家润整理 lifecycle side table 字段、事件 schema 和 summary 口径；王允配合验证日志输出和结果汇总路径。 | 完成 lifecycle 探针、side table 封装和 JSONL 事件日志，项目从合成闭环进入真实 vLLM 控制面观测阶段。 | [log](logs/2026-05-31.md)，[iteration log](docs/current/kvfabric_iteration_log.md) |
| 长对话压测与策略原型 | 2026-06-07 | 完成长时间对话压测设计和实现，并初步加入 KVFabric 策略进行验证。 | 王允完善 `experiments/langtime_running_test/` 长时间对话压测、多轮分叉和压力模式；赵天翔接入 `shared_aware`、`family_protect`、admission control 并运行 A/B；周家润整理模板 family、cache pressure、ordinary unique cold 等测试配置和对比报告口径。 | 长时间对话压测程序完成；初步策略验证通过，普通场景低开销退化，模板/多轮回访场景可减少共享主干误驱逐、提高 prefix-hit tokens。 | [log](logs/2026-06-07.md)，[prebenchmark validation](experiments/prebenchmark_validation/README.md) |
| 远程大规模实验准备 | 2026-06-15 | 讨论远程服务器实验平台，决定在 2 x RTX 3090 上开展长周期实验，并重跑早期实验用于对照。 | 周家润主要负责服务器部署、启动、运行和结果同步；小组共同确定 Qwen3.5-9B 作为后续主实验模型，Qwen3.5-27B 保留为高压力探索和历史对照。 | 建立从本地短测到远程长测的迁移计划，明确 deploy / runner / sync / summary / run root 归档闭环。 | [log](logs/2026-06-15.md)，[long pressure benchmark](experiments/long_pressure_benchmark/README.md) |
| 指标、请求模型与调试工具 | 2026-06-15 ~ 2026-06-22 | 设计更合理的评测指标、请求类型和真实化 trace，完善远程调试工具。 | 周家润在服务器上持续运行实验并反馈问题；赵天翔围绕 admission、scheduler、metrics 和 header plumbing 修改代码；王允配合整理 workload 场景和可视化/报告材料。 | 增加 e2e/class/segment/SLO goodput、rebuilt-from-eviction、lifecycle summary；实现 tenant/family/session/turn/phase trace、open-loop replay、duration loadgen、远程 runner、结果同步和 summary。 | [log](logs/2026-06-22.md)，[9B 实验设计](docs/current/kvfabric_qwen9b_experiment_design_2026-06-30.md) |
| 批量实验、dashboard 与最终矩阵 | 2026-06-22 ~ 2026-06-29 | 进行批量远程实验，定位策略在真实压力下的问题，收敛最终 12h 实验矩阵。 | 周家润负责批量远程实验、dashboard 运行和结果归档；赵天翔修正 admission 进入位置、scheduler promotion、latency guard 和 header whitelist；王允配合提炼展示场景与实验说明。 | 完成 run state、heartbeat、rolling metrics、dashboard 和 lifecycle replay；将策略抽象为 Admission / Eviction / Schedule / SLO protect controller；形成高压吞吐、企业混合、多轮长对话、低复用保护四类最终 stage。 | [log](logs/2026-06-29.md)，[6 月迭代历史](docs/current/kvfabric_june_iteration_history_2026-06-30.md)，[dashboard design](docs/current/kvfabric_dashboard_replay_design_2026-06-28.md) |
| 期末汇报整理 | 2026-06-30 ~ 2026-07-01 | 讨论期末汇报内容和分工，整理当前代码设计、接手后的迭代过程、调试工具、实验设计和结果展示。 | 小组共同整理报告材料；周家润整合前期开发、背景与最终 PPT；赵天翔整理后期迭代、实验设计、12h 结果和代码设计；王允补充实验工具和结果说明。 | 完成期末汇报材料归档，README、日志、roadmap 和 current docs 更新到 7 月 1 日状态。 | [log](logs/2026-06-30_2026-07-01.md)，[期末汇报 PPT](docs/endterm/KVFabric期末汇报.pptx) |

更详细的日期记录见 [logs/README.md](logs/README.md) 和 [docs/current/kvfabric_iteration_log.md](docs/current/kvfabric_iteration_log.md)。

## 实验体系

当前实验体系分为三层：

- 本地 smoke test：使用小模型和短 trace 验证代码路径、指标输出和策略开关。
- 中等规模远程实验：在 2 x RTX 3090 上使用 Qwen3.5-9B 跑 10~90 分钟实验，快速验证 workload、SLO、admission 和 scheduler 变更。
- 完整 12h 实验矩阵：使用统一 KVFabric controller 参数，在多个 stage 中覆盖高压吞吐、企业混合、多轮长对话和低复用保护场景，作为最终验收结果来源。

| 实验层级 | 目录/入口 | 模型与规模 | 主要作用 | 典型输出 |
| --- | --- | --- | --- | --- |
| lifecycle policy loop | `experiments/benchmarks/lifecycle_policy/` | 纯 Python 合成闭环 | 解释 side table、retain score、LRU vs shared-aware、eviction regret 和 TTFT/吞吐代理 | `metrics.json`、`eviction_events.jsonl`、`summary.md` |
| 本地 vLLM 预验证 | `experiments/prebenchmark_validation/` | Qwen3.5-2B，本地短 trace | 验证 overlay、prefix hit、KV pressure、lifecycle JSONL、Prometheus metrics 和小规模 A/B | lifecycle summary、Prometheus summary、`ab_comparison.md` |
| 长对话压测 | `experiments/langtime_running_test/` | 多轮对话、persona、dataset、pressure | 构造 continuous、random topic、persona rotation、multi-turn fork 等长上下文复用场景 | 对话记录、latency、token 统计、长对话运行日志 |
| 远程 9B 中等实验 | `experiments/long_pressure_benchmark/` | Qwen3.5-9B，10~90 分钟 | 校准 workload、SLO、capacity、admission、scheduler 和 hint 参数 | run root、class metrics、segment metrics、SLO probe |
| 远程 12h 矩阵 | `run_remote_qwen3_5_9b_12h_matrix_benchmark.sh` | Qwen3.5-9B，2 x RTX 3090 | 作为最终验收主结果，覆盖高压吞吐、企业混合、多轮长对话和低复用保护 | final summary、dashboard/replay 截图、SLO goodput、lifecycle evidence |
| 远程 27B 探索 | 27B remote scripts | Qwen3.5-27B-FP8，2 x RTX 3090 | 观察更紧张显存条件下的压力特征，保留历史对照 | 27B run summary、压力实验日志 |

推荐的代表性 A/B 场景：

- `ordinary_unique_cold.json`：普通无共享请求 sanity check，重点看低开销和非回归。
- `template_family_revisit.json`：模板 family 单周期回访，重点看共享主干保护。
- `template_family_revisit_cycles.json`：模板 family 多周期回访，重点看长期 prefix reuse。
- `cache_pressure_ambiguous_hot_revisit.json`：冷热混淆高压回访，重点看 eviction quality。
- `qwen3_5_9b_saturation_medium_60m.json`：9B 中等容量高压吞吐实验，重点看 SLO goodput 和 rebuilt。
- `qwen3_5_9b_enterprise_normal_75m.json` / `25m`：企业混合流量，重点看 foreground、background、cold RAG 和 session class 差异。
- `qwen3_5_9b_interactive_latency_queue_45m.json`：交互延迟和 queue pressure，重点看 scheduler affinity 与 latency guard。
- `qwen3_5_9b_low_reuse_low_frequency_20m.json`：低复用保护，重点看额外开销和退化风险。

核心实验文档：

- [9B 实验设计](docs/current/kvfabric_qwen9b_experiment_design_2026-06-30.md)
- [6 月迭代历史](docs/current/kvfabric_june_iteration_history_2026-06-30.md)
- [最终代码设计与 vLLM 对比](docs/current/kvfabric_final_code_design_vs_vllm_2026-06-30.md)
- [长周期压测工具](experiments/long_pressure_benchmark/README.md)
- [期末汇报 PPT](docs/endterm/KVFabric期末汇报.pptx)

## 与 vLLM 的关系

KVFabric 保留 vLLM 的执行模型、block 分配路径、prefix cache hash 机制和 OpenAI serving 接口，在其上增加控制面 overlay：

- vLLM 负责模型执行、KV block 分配、prefix cache 查找和请求调度的主流程。
- KVFabric 记录 block 为什么有价值、何时被复用、被驱逐后是否造成重建，以及请求是否值得优先调度。
- 策略通过参数化 controller 打开或调节，便于在同一套代码中比较 baseline、局部机制和完整策略。

这种实现方式降低了对 vLLM 主干的侵入性，也方便对照原始 vLLM 行为定位收益来源。

## 运行入口

常用入口集中在 `experiments/long_pressure_benchmark/`：

- `examples/online_trace_loadgen.py`：按 trace 中的 `scheduled_at_seconds` open-loop 发送请求。
- `examples/online_duration_loadgen.py`：按持续时间生成混合请求。
- `tools/`：trace 生成、远程运行、结果同步、summary、SLO goodput 和可视化辅助脚本。
- `scripts/`：远程部署、启动、归档和批量实验脚本。

具体命令和参数以对应目录 README 为准。

## 当前实现入口

```text
KVFabric/
├─ vllm_baseline/                         # vLLM baseline 环境、服务和 metrics 脚本
├─ vllm_workspace/
│  ├─ overlay/                            # vLLM Python 控制面 KVFabric overlay
│  ├─ scripts/                            # overlay 应用、同步和 patch 导出
│  └─ patches/                            # overlay patch
├─ experiments/
│  ├─ prebenchmark_validation/            # 本地 vLLM 在线请求、A/B、lifecycle summary
│  ├─ long_pressure_benchmark/            # 远程 9B/27B 长测、trace、loadgen、dashboard、replay
│  ├─ benchmarks/lifecycle_policy/         # 纯 Python 生命周期策略最小闭环
│  ├─ langtime_running_test/               # 长时间对话压测程序
│  └─ paper_reproductions/                 # 性能和质量评测复现入口
├─ docs/
│  ├─ current/                             # 当前实现计划、迭代日志、实验设计和交接说明
│  ├─ architecture/                        # 架构说明
│  ├─ reports/                             # 可行性报告和阶段报告
│  └─ research/                            # 调研材料
└─ logs/                                   # 小组讨论和阶段实现日志
```

核心代码改造集中在：

- `vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py`：维护 lifecycle side table、JSONL 事件日志、retain score、family-protect 选择器和 admission 状态。
- `vllm_workspace/overlay/vllm/v1/core/kvfabric_family.py`：维护 prefix family 的 root、parent、branch 和 protected depth 元数据。
- `vllm_workspace/overlay/vllm/v1/core/kvfabric_hints.py`：解析 request class、cache priority、expected reuse、tenant、family、session 和 SLO hint。
- `vllm_workspace/overlay/vllm/v1/core/block_pool.py`：接入 block sealed、touch、free、evict 和候选选择逻辑。
- `vllm_workspace/overlay/vllm/v1/core/single_type_kv_cache_manager.py`：承载 admission limit 的唯一实际入口，避免多处 double-limit 破坏 block hash 一致性。
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py`：记录 request 级 prefix lookup、prompt tokens 和 hit tokens。
- `vllm_workspace/overlay/vllm/v1/core/sched/scheduler.py`：接入 hit-aware waiting queue scan、promotion scoring、age guard、defer cap 和 latency-protected class。
- `vllm_workspace/overlay/vllm/v1/metrics/`：导出 block lookup、eviction、rebuilt、metadata overhead、waiting queue、class metrics 和 SLO 相关指标。

## 开发约定

- 代码修改优先保持 vLLM 原有结构，KVFabric 逻辑集中在 overlay、side table、controller 和实验工具链中。
- 新策略需要给出可观测指标，至少包含 lifecycle 事件、class/segment summary 或 SLO goodput 中的一项。
- 长测目录需要包含配置、run state、heartbeat、summary 和关键日志，避免只凭目录存在判断实验完成。
- 汇报和报告中的结论需要能追溯到具体 run、trace、summary 或 dashboard 数据。
