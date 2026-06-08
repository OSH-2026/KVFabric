# KVFabric

> 基于 vLLM Python 控制面的 KVCache 生命周期管理、共享感知驱逐与长对话压测原型

[English README](README_en.md) | [Architecture](docs/architecture/overview.md) | [Current Iteration Log](docs/current/kvfabric_iteration_log.md) | [vLLM Overlay](vllm_workspace/README.md) | [Prebenchmark Validation](experiments/prebenchmark_validation/README.md) | [Research Report](docs/research/group_research/research_report.md) | [Feasibility Report](docs/reports/feasibility_report.md)

KVFabric 是一个围绕 LLM serving 中 KVCache 生命周期管理展开的系统项目。当前项目已经在 vLLM Python 控制面中实现了一个可运行、可观测、可 A/B 对比的 KVCache 管理原型。

项目核心目标是：把 KV block 从“被动缓存页”提升为“具有状态、共享关系和保留价值的系统对象”。在 vLLM 原有 prefix caching 基础上，KVFabric 通过 lifecycle side table、事件日志、prefix family 统计、共享主干保护和驱逐后重建反馈，区分高价值共享前缀与低复用私有尾部，并在显存压力下优先保护长期可复用的 KV block。

## 项目成员

- [周家润](https://github.com/QY-dream)
- [赵天翔](https://github.com/ZTX1115)
- [王允](https://github.com/mjswyy)

---

## 项目阶段进展

|            项目阶段             |    日期     |        项目进展         |                                                                                                                        具体分工                                                                                                                         |       完成情况        | 附录                                |
|:---------------------------:|:---------:|:-------------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:-----------------:| ----------------------------------- |
|个人选题调研 |2026-03-23|组内线上会议，交流个人选题想法|了解当前各类可行的选题方向，讨论可行性|决定会议后个人进行选题调研，并在之后的组内会议中交流讨论，形成初步的选题方向|[log](logs/2026-03-23.md)|
|选题|2026-03-28|线下会议，交流选题想法，确定项目方向|周家润：基于eBPF的KV Cache性能剖析器在AIOS/vLLM中的简单实现与瓶颈分析；赵天翔：面向loong arch自研CPU编写可运行验证性应用承载型操作系统[调研报告](docs/research/individual_research/ZhaoTianxiang/ztx_research1.md)；王允：用RUST语言改写一门简单的操作系统|决定采用在loong arch架构开发板上编写可运行验证性操作系统|[log](logs/2026-03-28.md)|
|选题|2026-03-28|线上会议|向老师报告选题并咨询意见|选题被驳回，需要重新选题||
|选题|2026-03-29|组员分别进行调研，并开展线上会议进行讨论|周家润：[调研报告](docs/research/individual_research/ZhouJiarun/zjr_research.md)，选题：KV Cache统一生命周期管理 + chunk 级复用 + CoW 分叉；赵天翔：[调研报告](docs/research/individual_research/ZhaoTianxiang/ztx_research2.md)，选题：⾯向 LLM 推理服务的 KVCache 分配、复⽤与驱逐协同优化；王允：[调研报告](docs/research/individual_research/WangYun/wy_research.md)，选题：面向移动端的轻量AI用户态调度引擎设计与实现|经讨论决定采用“KV Cache统一生命周期管理 + chunk 级复用 + CoW 分叉”的选题|[log](logs/2026-03-29.md)|
|选题|2026-03-29|线上会议|向老师报告选题并咨询意见|选题通过||
|学习|2026-04-07|学习LLM推理与KVCache分析相关知识，并选择实现平台|周家润：[KVFabric 小组研究报告](docs/research/group_research/research_report.md)；赵天翔：[vLLM 与 llama.cpp 适用性调研](docs/research/individual_research/ZhaoTianxiang/ztx_research3.md)；王允：[vllm与llamacpp平台的优缺点比较](docs/research/group_research/vllm-vs-llamacpp.md)|完成初步学习，决定在vllm上实现该项目|[log](logs/2026-04-07.md)|
|项目搭建|2026-04-13|搭建vLLM基线环境，打通推理链路|周家润：环境搭建、推理链路打通、性能数据收集；赵天翔：撰写[可行性报告](docs/reports/feasibility_report.md)；王允：整理日志和文档|成功搭建vLLM环境，并完成了端到端的推理链路验证，收集了初步的性能数据|[log](logs/2026-04-14-vllm-bringup.md)|
|小组讨论|2026-04-19|线下会议|讨论后续的vLLM改造范围和设计思路，明确接下来的任务内容|下周三之前进行对vllm源码的阅读和分析，并决定在下周三开一次会议商量之后的具体分工|[log](logs/2026-04-19.md)|
|小组讨论|2026-04-23|线下会议，确定后续任务是详细阅读一些前沿顶会论文，获取他们的评测量化方法，并复现项目相关的关于vllm和KVcache性能评测测试|周家润：[KVCache 压缩与质量评测](logs/2026-04-23_work.md#L71)；赵天翔：[KVCache 复用与前缀缓存评测](logs/2026-04-23_work.md#L33)；王允：[vLLM 的标准基础服务性能评测](logs/2026-04-23_work.md#L1)|王允：[评测工具](docs/reports/first_test_report/wangyun/vllm_test_tool_analysis.md)、[测试结果](docs/reports/first_test_report/wangyun/benchmark_results/baseline_benchmark_report.md)、[测试流程](experiments/paper_reproductions/vllm_performance_benchmark/README.md)。周家润：...赵天翔：...|[log](logs/2026-04-23.md)|
|小组讨论|2026-4-28|线下会议，KVCache相关指标评测方法以实现，准备进行中期汇报。|周家润负责中期汇报PPT的设计与制作，赵天翔和王允负责在中期汇报中对别的组的项目进行了解与提问。|周家润：[PPT](docs/media/KVFabric_midterm_report.pptx)|[log](logs/2026-04-28.md)|
|中期汇报|2026-05-06|课上中期汇报汇报当前项目进展并回答相关问题。|周家润与赵天翔汇报PPT与回答问题，王允负责记录同学与老师的问题与建议。|老师给出[后续路径规划和建议](logs/参考.md)|[log](logs/2026-05-06.md)|
|小组讨论|2026-05-09|线下会议，讨论后续规划|开始打造最小闭环，由赵天翔负责|[纯 Python、确定性可复现的最小闭环](experiments/benchmarks/lifecycle_policy/README.md)|[log](logs/2026-05-09.md)|
|小组讨论|2026-05-24|线下会议，开始对vllm源码进行改造|赵天翔向原码中加入探针，监测KVblock状态。周家润实现对数据的封装。王允负责准备长时间测试所需数据集|[长时间对话压测程序](experiments/langtime_running_test/README.md)||
|小组讨论与工作实现|2026-05-31|初步完成 vLLM 控制面生命周期探针和封装|赵天翔：完善 `kvfabric_lifecycle.py`，在 `BlockPool`、`KVCacheManager` 中接入 prefix lookup、block sealed、touch、evict 等事件；周家润：整理 lifecycle side table 字段、事件 schema 和 summary 口径；王允：配合验证日志输出和结果汇总路径|完成 lifecycle 探针、side table 封装和 JSONL 事件日志，项目从合成闭环进入真实 vLLM 控制面观测阶段|[log](logs/2026-05-31.md)|
|小组讨论与工作实现|2026-06-07|完成长时间对话压测部分的设计和实现，并初步加入 KVFabric 策略进行验证|王允：完善 `experiments/langtime_running_test/` 长时间对话压测、多轮分叉和压力模式；赵天翔：接入 `shared_aware`、`family_protect`、admission control 并运行 A/B；周家润：整理模板 family、cache pressure、ordinary unique cold 等测试配置和对比报告口径|长时间对话压测程序完成；初步策略验证通过，普通场景低开销退化，模板/多轮回访场景可减少共享主干误驱逐、提高 prefix-hit tokens|[log](logs/2026-06-07.md)|

## 当前状态

当前阶段已经完成从“基线跑通”到“vLLM 控制面原型验证”的推进：

- 已跑通官方 vLLM baseline，包括 offline inference、OpenAI-compatible serving 和基础 metrics 读取。
- 已完成 KVCache 生命周期探针和封装：block 分配、sealed、touch、ref count、evict、rebuilt-from-eviction 等事件可通过 JSONL 记录。
- 已在 `vllm_workspace/overlay/` 中加入 KVFabric lifecycle tracker、Prometheus 指标探针、`shared_aware` 和 `family_protect` 策略分支。
- 已构建 `experiments/prebenchmark_validation/` A/B 工具链，可比较 vLLM LRU 路径与 KVFabric 策略路径。
- 已完成长时间对话压测程序的设计与实现，为多轮、长上下文、相似对话和压力场景提供测试入口。
- 已在模板化 prompt、相似多轮回访等场景中观察到 KVFabric 能减少共享主干误驱逐，提高 prefix-hit tokens，并带来小幅端到端收益。

当前更稳妥的阶段性结论是：

- 普通无共享请求中，KVFabric 能退化为低开销路径。
- 模板化 prompt、相似多轮对话、长期共享前缀回访等场景中，KVFabric 能明显改善 eviction quality。
- 当前收益主要体现在 `rebuilt-from-eviction` 下降、prefix-hit tokens 增加、TTFT/E2E latency 改善和 requests/s 小幅提升。
- 当前还不能宣称所有 workload 都有大幅吞吐提升；项目重点是解释性 KVCache 资源管理，而不是单一 raw throughput 优化。

## 项目方向

KVFabric 当前的项目方向是围绕 vLLM 中 KVCache 的生命周期管理做一个可观测、可解释、可对照的系统原型。项目不只是打开 prefix caching，也不是只在显存不足时临时决定驱逐谁，而是持续记录 KV block 从创建、写满、进入 prefix cache、被共享、引用归零、进入候选、被驱逐到后续重建的过程。

当前实现主要落在 vLLM Python 控制面：

- `vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py`：维护 lifecycle side table、JSONL 事件日志、retain score、family-protect 选择器和 admission gate。
- `vllm_workspace/overlay/vllm/v1/core/block_pool.py`：接入 block sealed、touch、free、evict 和候选选择逻辑。
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_manager.py`：记录 request 级 prefix lookup、prompt tokens 和 hit tokens。
- `vllm_workspace/overlay/vllm/v1/core/kv_cache_metrics.py` 与 `vllm_workspace/overlay/vllm/v1/metrics/`：导出 block lookup、eviction、rebuilt、metadata overhead 等指标。

策略方向分为三层：

- 生命周期封装：把 KV block 的状态和共享关系写入 side table，使后续实验能解释每一次命中、释放和驱逐。
- 共享主干保护：通过 `hit_count`、`share_degree`、`branch_factor`、`prefix_depth` 等信号识别长期可复用的 prefix family，优先保护共享主干，避免把高价值公共前缀当作普通 LRU block 回收。
- 调度与评测联动：通过 `experiments/prebenchmark_validation/`、`experiments/langtime_running_test/` 和 lifecycle JSONL/Prometheus 指标，把策略行为和请求级 TTFT、E2E latency、requests/s、prefix-hit tokens 对齐分析。

后续整理重点是保留清晰的 A/B 证据：普通无共享场景中策略应低开销退化；模板化 prompt、相似多轮对话和长期共享前缀回访场景中，策略应减少共享主干误驱逐和 rebuilt-from-eviction，提高 prefix-hit tokens，并解释这些收益来自哪里。

## 核心设计

### 生命周期封装

KVFabric 在 vLLM 控制面维护一张 lifecycle side table，把每个 KV block 的运行状态转化为可观测对象。当前记录的核心字段包括：

- block id 与 block hash；
- prefix depth 与 recompute cost；
- ref count、hit count、share degree、branch factor；
- 当前生命周期状态；
- 驱逐时 retain score；
- 驱逐后同 hash 是否很快重建。

这些字段不改变 worker 侧 block table 或 attention kernel 语义，主要用于观测、策略选择和实验解释。

### 共享主干与私有尾部

在严格 prefix caching 语义下，多个请求可能共享完整 full-block 前缀，之后追加不同的私有尾部。KVFabric 将这类结构抽象为 prefix family：

- 共享主干 block：通常位于 prompt 前段，可能被模板、RAG 文档、多轮历史反复复用，应优先保护。
- 私有尾部 block：通常属于单个请求的后缀，长期复用概率低，更适合作为驱逐候选。
- 分叉代理指标：通过 `share_degree`、`hit_count`、`branch_factor` 和 `prefix_depth` 近似描述共享结构价值。

### 共享感知驱逐策略

当前 overlay 中保留两类策略：

- `shared_aware`：基于 retain score 对候选 block 做排序，优先驱逐低保留价值 block。
- `family_protect`：轻量保护长期复用 family。它保持 vLLM free queue 的原始顺序，只在候选中遇到 protected block 时延后驱逐，避免无压力场景产生额外排序开销。

策略开关由环境变量控制，默认可退回 vLLM 原行为。典型变量包括：

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
KVFABRIC_EVICTION_POLICY=lru|shared_aware|family_protect
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

### 事件日志与指标

KVFabric 当前支持两条观测链路：

- JSONL lifecycle events：用于实验后处理和策略解释。
- Prometheus metrics：用于请求级和 block 级指标汇总。

关键事件包括：

- `prefix_lookup`
- `block_allocated`
- `block_sealed`
- `block_touched`
- `ref_count_changed`
- `cache_admission_limited`
- `eviction_candidates_ranked`
- `block_evicted`

关键指标包括：

- prefix hit rate / prefix-hit tokens；
- evicted blocks；
- shared-anchor eviction ratio；
- protected eviction ratio；
- rebuilt-from-eviction blocks；
- regretful eviction proxy；
- TTFT、TPOT、E2E latency、requests/s；
- metadata update overhead 与 block lookup overhead。

## 当前实现入口

```text
KVFabric/
├─ vllm_baseline/                         # vLLM baseline 环境、服务和 metrics 脚本
├─ vllm_workspace/
│  ├─ overlay/                            # vLLM Python 控制面 prototype overlay
│  ├─ scripts/                            # overlay 应用、同步和 patch 导出
│  └─ patches/                            # overlay patch
├─ experiments/
│  ├─ prebenchmark_validation/            # vLLM 在线请求、A/B、lifecycle summary
│  ├─ benchmarks/lifecycle_policy/         # 纯 Python 生命周期策略最小闭环
│  ├─ langtime_running_test/               # 长时间对话压测程序
│  └─ paper_reproductions/                 # 性能和质量评测复现入口
├─ docs/
│  ├─ current/                             # 当前实现计划、迭代日志和交接说明
│  ├─ architecture/                        # 架构说明
│  ├─ reports/                             # 可行性报告和测试报告
│  └─ research/                            # 调研材料
└─ logs/                                   # 小组讨论和阶段实现日志
```

## 实验与验证

当前实验分为三层：

1. `experiments/prebenchmark_validation/`
   - 验证真实 vLLM serving 下的 prefix hit、KV pressure、lifecycle JSONL 和 A/B 行为。
   - 关键脚本：`run_kvfabric_ab_smoke.sh`、`summarize_kvfabric_lifecycle.py`、`compare_kvfabric_ab.py`。

2. `experiments/benchmarks/lifecycle_policy/`
   - 纯 Python 合成闭环，用来解释生命周期建模、LRU vs shared-aware、eviction regret 和 TTFT/吞吐代理。
   - 它不宣称真实 GPU 性能收益，只用于验证策略思想。

3. `experiments/langtime_running_test/`
   - 长时间对话压测程序，覆盖 continuous、random topic、persona rotation、dataset driven、pressure test、multi-turn fork 等模式。
   - 用于构造更接近长对话和多轮服务的 KV reuse 场景。

推荐的代表性 A/B 场景：

- `ordinary_unique_cold.json`：普通无共享请求 sanity check。
- `template_family_revisit.json`：模板 family 单周期回访。
- `template_family_revisit_cycles.json`：模板 family 多周期回访。
- `cache_pressure_ambiguous_hot_revisit.json`：冷热混淆高压回访。

## 文档入口

- [当前迭代日志](docs/current/kvfabric_iteration_log.md)
- [源码修改与团队计划](docs/current/source_modification_and_team_plan.md)
- [3090 复跑交接](docs/current/3090_handoff.md)
- [vLLM Overlay 工作区](vllm_workspace/README.md)
- [Prebenchmark Validation](experiments/prebenchmark_validation/README.md)
- [生命周期策略最小闭环](experiments/benchmarks/lifecycle_policy/README.md)
- [长时间对话压测](experiments/langtime_running_test/README.md)
- [可行性报告](docs/reports/feasibility_report.md)

## License

MIT
