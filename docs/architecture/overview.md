# Architecture Overview

## 项目定位

KVFabric 的长期目标不是停留在“现有框架内的一层 Python 原型”，而是逐步走向：

> 做一个以 C++ 为核心实现语言、面向真实推理系统、强调可移植性的 KV Cache scheduler / runtime。

但就当前课程周期和 `vLLM` 源码切入点而言，如果要先实现“统一生命周期管理 / 共享感知驱逐 / 共享后分叉”的最小可行原型，应先在 `vLLM` 的 Python 控制面完成验证，再判断是否需要下沉到 C++/CUDA。

这里的“可移植”主要包含两层含义：

- 不把核心调度逻辑永久绑定在某一个 Python serving 框架内部；
- 为不同计算后端和宿主系统保留抽象边界，而不是把策略写死在单一路径里。

## 当前阶段原则

当前阶段的首要原则是：

> 在没有跑通、测明白、读清官方 vLLM 之前，不进入自研 C++ runtime 实现阶段。

因此，当前仓库只保留：

- 调研材料
- 架构说明
- vLLM 部署与测试计划
- 可复用的 `vllm_baseline/` 基线工作区
- 路线图与阶段日志

当前阶段不保留任何“看起来像成品”的自研调度器代码。

## 阶段性 vLLM 改造边界

基于当前已验证的 `vLLM 0.19.0` 和 `v1` 代码结构，短期若修改 `vLLM` 源码，主要应落在 Python 层：

- `vllm/v1/core/sched/scheduler.py`：请求调度、prefix hit 后的 token 计算状态、preemption 与分配调用入口。
- `vllm/v1/core/kv_cache_manager.py`：`get_computed_blocks`、`can_fit_full_sequence`、`allocate_slots`、`free`、`evict_blocks` 等 cache manager 对 scheduler 的主接口。
- `vllm/v1/core/block_pool.py`：`BlockPool`、free block queue、block hash 映射、缓存块驱逐入口。
- `vllm/v1/core/kv_cache_utils.py`：`KVCacheBlock`、block hash、free queue 等基础元数据结构。
- `vllm/v1/core/single_type_kv_cache_manager.py` 与 `vllm/v1/core/kv_cache_coordinator.py`：不同 KV cache group 下的分配、命中、释放和 skipped block 处理。
- `vllm/v1/metrics/` 相关路径：后续记录 prefix hit、block lifetime、eviction、recompute 等观测指标。

第一阶段应尽量避免直接修改：

- `vllm/_custom_ops.py` 背后的 C++/CUDA 扩展；
- `vllm/v1/attention/ops/` 中的 attention kernel 热路径；
- `vllm/v1/worker/block_table.py` 或 GPU model runner 中会改变底层 block table / slot mapping 语义的代码。

判断标准是：如果只是新增生命周期元数据、命中/驱逐统计、候选块打分、调度策略或 prefix-cache 复用决策，优先在 Python 层完成；只有当功能必须改变 KV cache 的物理布局、kernel 访问方式、跨 block 拷贝语义或真正的 in-kernel CoW 写入路径时，才进入 C++/CUDA 修改范围。

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

这一层长期计划由 `C++17/20` 实现，是后续最重要的主体代码。短期在 `vLLM` 内验证策略时，可先把同一套抽象以 Python side table、manager 扩展或调度策略的形式做成最小原型。

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
5. 先在 Python 控制面完成可验证原型
6. 再决定哪些能力应在未来的 KVFabric 中被保留、重构、下沉到 C++ 或替换

换句话说，vLLM 是当前阶段必须认真学习和验证的基础系统；短期可以作为 Python 层原型载体，但项目的长期目标不是停留为“另一个 vLLM patch set”。

## 当前非目标

以下内容在当前阶段都不是第一优先级：

- 提前写自研 runtime 代码
- 提前确定最终 API 细节
- 在 Python 控制面原型前直接改 C++/CUDA attention kernel
- 在尚未验证基线前讨论过细的微优化

## 当前阶段的产出要求

在进入自研实现前，当前阶段至少应完成：

- 一个仓库内可复用、可分享的 vLLM baseline workspace
- vLLM 本地部署记录
- 最小 offline / serving 测试记录
- 与 KV Cache 相关的关键调用链梳理
- benchmark 方案与指标清单
- 短期 `vLLM` Python 改造范围说明
- 面向长期 C++ 实现的模块边界说明
