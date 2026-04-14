# Architecture Overview

## 项目定位

KVFabric 的目标已经从“在现有框架内做一层 Python 原型”调整为：

> 做一个以 C++ 为核心实现语言、面向真实推理系统、强调可移植性的 KV Cache scheduler / runtime。

这里的“可移植”主要包含两层含义：

- 不把核心调度逻辑永久绑定在某一个 Python serving 框架内部；
- 为不同计算后端和宿主系统保留抽象边界，而不是把策略写死在单一路径里。

## 当前阶段原则

当前阶段的首要原则是：

> 在没有跑通、测明白、读清官方 vLLM 之前，不进入自研实现阶段。

因此，当前仓库只保留：

- 调研材料
- 架构说明
- vLLM 部署与测试计划
- 路线图与阶段日志

当前阶段不保留任何“看起来像成品”的自研调度器代码。

## 长期系统目标

未来的 KVFabric 希望具备以下能力：

1. 统一的 block 生命周期管理
2. 更强的共享、分叉与驱逐表达能力
3. 可解释的重算代价建模
4. 面向不同后端的抽象接口
5. 更清晰的性能观测与 benchmark 支撑

## 目标架构

```text
             +-----------------------------------+
             | Frontend / Engine Adapters        |
             | vLLM first, others later          |
             +-----------------+-----------------+
                               |
                               v
             +-----------------------------------+
             | KVFabric Scheduler Core (C++)     |
             | allocate / reuse / fork / evict   |
             +-----------------+-----------------+
                               |
                               v
             +-----------------------------------+
             | Metadata & Block Table            |
             | ref_count / state / cost / heat   |
             +-----------------+-----------------+
                               |
                               v
             +-----------------------------------+
             | Backend Abstraction               |
             | CUDA / ROCm / CPU / future        |
             +-----------------------------------+
```

## 目标模块

### 1. Scheduler Core

这是未来系统的核心，负责：

- block 分配
- 共享命中
- CoW 分叉
- 驱逐排序
- 生命周期状态流转

这一层计划由 `C++17/20` 实现，是后续最重要的主体代码。

### 2. Metadata & Block Table

未来需要统一维护至少以下信息：

- `RefCount`
- `ShareState`
- `AccessHistory`
- `RecomputeCost`
- `Prefix/Chunk Identity`

它不应只是某个框架内部的临时附属结构，而应成为 scheduler 的一等对象。

### 3. Backend Abstraction

如果项目要真正可移植，就不能默认调度逻辑与单一 CUDA 路径永久耦合。后续需要设计清晰边界，使以下内容可分层处理：

- 调度策略
- block 元数据管理
- 物理存储后端
- backend-specific memory operations

## 与 vLLM 的关系

当前短期内，`vLLM` 是基线与对照对象，不是最终形态。

项目对 vLLM 的使用顺序应当是：

1. 先部署官方版本
2. 跑通最小可用推理与服务
3. 读清相关代码路径
4. 明确其 scheduler / cache manager 的边界与不足
5. 再决定哪些能力应在未来的 KVFabric 中被保留、重构或替换

换句话说，vLLM 是当前阶段必须认真学习和验证的基础系统，但项目的长期目标不是成为“另一个 vLLM patch set”。

## 当前非目标

以下内容在当前阶段都不是第一优先级：

- 提前写自研 runtime 代码
- 提前确定最终 API 细节
- 直接承诺特定 attention kernel 实现
- 在尚未验证基线前讨论过细的微优化

## 当前阶段的产出要求

在进入自研实现前，当前阶段至少应完成：

- vLLM 本地部署记录
- 最小 offline / serving 测试记录
- 与 KV Cache 相关的关键调用链梳理
- benchmark 方案与指标清单
- 面向 C++ 实现的模块边界说明
