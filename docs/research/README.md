# Research Notes

本目录用于存放项目的前期调研材料，按 `group_research` 和 `individual_research` 两部分组织。

## Directory Layout

```text
docs/research/
├─ group_research/
│  ├─ research_report.md
│  └─ vllm-vs-llamacpp.md
└─ individual_research/
   └─ ZhouJiarun/
      └─ README.md
```

## Group Research

`group_research/` 存放小组共同使用和讨论的材料，当前包括：

- [research_report.md](group_research/research_report.md)
  小组完整研究报告，整合了 LLM 推理、KV Cache 机制、现存问题、生命周期管理、vLLM 选型与评测方案。
- [vllm-vs-llamacpp.md](group_research/vllm-vs-llamacpp.md)
  对 vLLM 和 llama.cpp 作为项目基座的对比结论。

## Individual Research

`individual_research/` 存放成员个人在前期方向探索阶段完成的调研记录。

- [ZhouJiarun/README.md](individual_research/ZhouJiarun/README.md)
  针对 `eBPF`、`协程调度器`、`KV Cache` 三个候选方向的个人调研报告，并给出最终方向收敛结论。

## Current Focus

当前调研部分已经完成“方向探索”和“问题收敛”的任务，后续主要作为前期依据保留。项目主线已经进入 vLLM overlay、远程 9B 实验和最终报告整理阶段：

- baseline、scheduler、prefix cache 与 KV Cache 管理路径的阅读结论沉淀在 `docs/baseline/`、`docs/architecture/` 和 `vllm_workspace/`。
- 6 月中下旬的实现迭代和实验复盘集中在 `docs/current/` 和 `logs/`。
- 远程 Qwen3.5-9B 长周期实验、dashboard、summary 和 replay 工具集中在 `experiments/long_pressure_benchmark/`。
- 本目录保留早期选型、平台比较和问题定义材料，不再作为当前进度跟踪入口。
