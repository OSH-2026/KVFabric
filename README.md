# KVFabric

> KV Cache scheduling for LLM serving, with a vLLM Python-control-plane prototype first and a portable C++ runtime as the long-term target

[English README](README_en.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Baseline Workspace](vllm_baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md) | [Research Report](docs\research\group_research\research_report.md) | [Feasibility Report](docs\reports\feasibility_report.md) |

KVFabric 是一个围绕 LLM serving 中 KV Cache 调度与生命周期管理展开的系统项目。仓库目前以 `vLLM` 基线为中心，先把部署、验证、代码路径和评测入口打磨清楚。需要修改 `vLLM` 源码来验证“统一生命周期管理 / 共享感知驱逐 / 共享后分叉”等功能，当前优先改 `vLLM` 的 Python 控制面代码。

## 项目成员

-   [周家润](https://github.com/QY-dream)
-   [赵天翔](https://github.com/ZTX1115)
-   [王允](https://github.com/mjswyy)

---

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
|小组讨论|2026-04-23|线下会议，确定后续任务是详细阅读一些前沿顶会论文，获取他们的评测量化方法，并复现项目相关的关于vllm和KVcache性能评测测试|周家润：[KVCache 压缩与质量评测](logs\2026-04-23_work.md#L71)；赵天翔：[KVCache 复用与前缀缓存评测](logs\2026-04-23_work.md#L33)；王允：[vLLM 的标准基础服务性能评测](logs\2026-04-23_work.md#L1)|王允：[评测工具](docs\reports\first_test_report\wangyun\vllm_test_tool_analysis.md)、[测试结果](docs\reports\first_test_report\wangyun\benchmark_results\baseline_benchmark_report.md)...|[log](logs/2026-04-23.md)|
---
## 当前状态

- 阶段：`baseline bring-up / architecture freeze`
- 基线引擎：官方 `vLLM`
- 已验证模型：`Qwen/Qwen3.5-2B`
- 可选模型：`Qwen/Qwen3-8B`
- 可运行入口：[vllm_baseline/README.md](vllm_baseline/README.md)
- 运行记录：[logs/2026-04-14-vllm-bringup.md](logs/2026-04-14-vllm-bringup.md)

目前仓库的重点很直接：

- 跑通官方 `vLLM` 的 offline inference 和 online serving
- 梳理 `scheduler / prefix cache / paged attention / hybrid cache` 等关键路径
- 明确短期 `vLLM` 原型改造主要落在 Python 层的 scheduler、KV cache manager、block pool 与元数据路径
- 用一套稳定、可复现的基线流程支撑后续 C++ 模块边界设计

## 项目方向

- 短期实现边界：若修改 `vLLM` 源码，优先修改 `vllm/v1/core/sched/`、`vllm/v1/core/kv_cache_manager.py`、`vllm/v1/core/block_pool.py`、`vllm/v1/core/kv_cache_utils.py`、`vllm/v1/core/single_type_kv_cache_manager.py` 等 Python 控制面
- 暂不优先修改：C++/CUDA attention kernel、底层 KV 物理布局和自定义算子，除非后续功能必须改变 block 内存布局、slot mapping 语义或 kernel 写入/拷贝路径
- 长期目标实现语言：`C++17/20`
- 长期目标形态：独立的 KV Cache scheduler / runtime
- 长期方向：在 portability、scheduler design 和 lifecycle management 上做出独立演进的系统方案

## 目标系统轮廓

```text
              +----------------------------------+
              | Frontend / Engine Adapters       |
              | (vLLM first, others later)       |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | KVFabric Scheduler Core (C++)    |
              | allocate / reuse / fork / evict  |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | Metadata / Block Table           |
              | ref count / state / cost / heat  |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | Backend Abstraction Layer        |
              | CUDA / ROCm / CPU / future       |
              +----------------------------------+
```

## 仓库结构

```text
KVFabric/
├─ .github/               GitHub templates
├─ docs/
│  ├─ architecture/       architecture notes
│  ├─ baseline/           project-level baseline docs
│  ├─ media/              figures and images
│  ├─ reports/            report placeholders
│  └─ research/           early research notes
├─ logs/                  bring-up and milestone logs
└─ vllm_baseline/         runnable vLLM baseline workspace
```

## 快速开始

如果你的目标是先把这套基线真正跑起来，直接从 `vllm_baseline/` 开始：

```bash
cd KVFabric
cd vllm_baseline

bash scripts/setup_venv.sh
bash scripts/download_model.sh qwen3_5_2b
bash scripts/run_offline_smoke.sh qwen3_5_2b
bash scripts/serve_local.sh qwen3_5_2b
bash scripts/verify_server.sh qwen3_5_2b
bash scripts/stop_server.sh qwen3_5_2b
```

默认验证链路使用 `Qwen/Qwen3.5-2B`。`Qwen/Qwen3-8B` 作为可选预设保留，更适合更大显存机器做后续对照。

## 当前仓库包含

- `vllm_baseline/`：环境配置、模型下载、offline smoke test、local serving、API 验证
- `docs/architecture/`：未来 runtime 的模块边界与系统轮廓
- `docs/baseline/`：项目层面的 baseline 目标、约束与退出条件
- `docs/evaluation-plan.md`：基线评测计划
- `logs/`：已完成的 bring-up 记录和后续阶段日志

## 当前暂不包含

- 自研 KVFabric runtime 源码
- 已落地的 `vLLM` patch 集
- C++/CUDA kernel 改动
- 独立聊天前端或展示 UI

## 文档

- [Architecture Overview](docs/architecture/overview.md)
- [vLLM Baseline](docs/baseline/README.md)
- [vLLM Baseline Workspace](vllm_baseline/README.md)
- [Evaluation Plan](docs/evaluation-plan.md)
- [Roadmap](docs/roadmap.md)
- [Research Notes](docs/research/README.md)

## License

MIT
