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

当前调研部分已经完成从“方向探索”到“问题收敛”的过渡。接下来研究工作的重点不再是提前写自研框架代码，而是：

- 本地部署并验证官方 `vLLM`
- 读清其 scheduler、prefix cache 与 KV Cache 管理路径
- 如果进入源码原型，优先在 `vLLM` Python 控制面验证生命周期元数据、共享感知驱逐和观测指标
- 为后续以 `C++` 为核心实现语言的自研系统冻结模块边界
