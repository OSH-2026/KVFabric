# KVFabric

> A portable, C++-first KV Cache scheduling project for LLM serving systems

[English README](README_en.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md)


## 项目简介

KVFabric 是一个面向 LLM 推理服务的 KV Cache 调度项目，目标不是简单地在现有框架上补若干策略，而是做一套 **真正可移植、可独立演进、以 C++ 为核心实现语言** 的 KV Cache 调度与生命周期管理系统。

项目长期目标是围绕 KV block 的 **分配、共享、分叉、驱逐、重算代价建模** 建立统一的调度框架，并在可移植性、调度表达能力和工程可用性上，做出比现有 vLLM 默认方案更强的系统设计。

## 当前阶段

仓库当前处于 **baseline bring-up / architecture freeze** 阶段，核心任务不是立刻写自研调度器代码，而是先把官方 vLLM 本体在本地或等价 Linux 环境中完整部署、跑通和测明白。

这一阶段的重点包括：

- 本地部署并验证官方 `vLLM`
- 跑通最小离线推理与在线服务
- 读清 `scheduler / prefix cache / paged attention / hybrid cache` 等关键路径
- 明确 vLLM 的现有边界和不足
- 在此基础上冻结未来自研 C++ 系统的模块边界

因此，仓库中当前 **不保留自研运行时或调度器实现代码**，以避免在基线尚未建立之前过早进入错误实现方向。

## 项目目标

### 长期目标

- 构建一个以 `C++` 为主实现语言的 KV Cache 调度系统
- 让核心调度逻辑尽可能摆脱对单一 Python serving 框架的依赖
- 支持更清晰的 block 生命周期管理和更强的可观测性
- 为后续跨后端或跨框架适配留下空间

### 中期目标

- 提炼 vLLM 当前 KV Cache 路径中的关键约束
- 形成自己的 block metadata、scheduler API 和 backend abstraction 设计
- 明确哪些部分要复用现有 serving 框架，哪些部分应独立实现

### 当前目标

- 本地部署并测试 vLLM
- 记录部署约束、运行方式和 benchmark 结果
- 产出面向后续 C++ 实现的系统设计文档

## 目标方向调整

本项目当前已经明确转向以下路线：

- **实现语言**：以 `C++17/20` 为主，必要时辅以少量 Python 绑定或测试脚本
- **系统定位**：独立的 KV Cache scheduler / runtime，而不是仅仅做 Python 层策略补丁
- **短期基线**：先完整理解并验证官方 `vLLM`
- **长期目标**：在 portability、scheduler design 和 lifecycle management 上超越现有 vLLM 默认方案

## 目标系统轮廓

```text
              +----------------------------------+
              | Frontend / Engine Adapters       |
              | (vLLM baseline first, others later) |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | KVFabric Scheduler Core (C++)    |
              | - allocation                     |
              | - reuse                          |
              | - fork / CoW                     |
              | - eviction                       |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | Metadata / Block Table           |
              | - ref count                      |
              | - share state                    |
              | - recompute cost                 |
              | - access history                 |
              +----------------+-----------------+
                               |
                               v
              +----------------------------------+
              | Backend Abstraction Layer        |
              | CUDA / ROCm / CPU / future       |
              +----------------------------------+
```

## 当前仓库内容

```text
KVFabric/
├─ .github/               GitHub 模板
├─ docs/
│  ├─ architecture/       目标架构与模块边界
│  ├─ baseline/           vLLM 本地部署与验证计划
│  ├─ media/              图片与示意图
│  ├─ reports/            报告占位
│  └─ research/           前期调研材料
└─ logs/                  阶段日志
```

## 文档索引

- [Architecture Overview](docs/architecture/overview.md)
- [vLLM Baseline Plan](docs/baseline/README.md)
- [Evaluation Plan](docs/evaluation-plan.md)
- [Roadmap](docs/roadmap.md)
- [Research Notes](docs/research/README.md)

## 本阶段不做什么

- 不提前写一版“看起来像框架”的自研代码
- 不在尚未验证 vLLM 基线前直接承诺具体实现细节
- 不把项目限制在单纯的 Python control plane patch 上

## License

MIT
