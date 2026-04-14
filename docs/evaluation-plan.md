# Evaluation Plan

## Phase 1: Official vLLM Baseline

当前第一阶段不是评测自研系统，而是评测和记录官方 vLLM 基线。

当前仓库内已经提供统一执行入口：

- `vllm_baseline/scripts/`
- `vllm_baseline/examples/`
- `logs/2026-04-14-vllm-bringup.md`

### Baseline targets

- vanilla `vLLM` offline inference
- vanilla `vLLM` OpenAI-compatible serving
- prefix caching enabled / disabled when possible
- repository-local reproducible bring-up flow

### Workloads

#### 1. Minimal smoke test

目标：

- 验证模型可加载
- 验证 offline inference 和 online serving 都可正常工作

当前默认使用：

- `Qwen/Qwen2.5-0.5B-Instruct`

当前可选使用：

- `Qwen/Qwen3-8B`，但更适合更大显存机器

#### 2. Template-heavy prompts

目标：

- 观察 prefix caching 的基础行为
- 记录相似 prompt 下的吞吐和内存变化

#### 3. Multi-turn / long-context style workload

目标：

- 观察长上下文压力下的服务表现
- 为未来 KV Cache scheduler 设计收集第一手基线数据

### Phase 1 metrics

- startup success / failure
- model load time
- tokens per second
- request latency
- peak memory usage
- prefix reuse related observations
- whether the shared workspace scripts reproduce the same behavior across machines

## Phase 2: Future KVFabric Comparison

在官方 vLLM 基线稳定、并且自研系统开始实现后，再进入第二阶段对比：

- `official vLLM`
- `future KVFabric runtime / scheduler`

届时重点关注：

- portability
- scheduler flexibility
- lifecycle visibility
- reuse / fork / eviction behavior
- memory efficiency under mixed workloads
