# KVFabric

> KV Cache scheduling for LLM serving, with a portable C++ runtime as the long-term target

[English README](README_en.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Baseline Workspace](vllm_baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md)

KVFabric 是一个围绕 LLM serving 中 KV Cache 调度与生命周期管理展开的系统项目。仓库目前以 `vLLM` 基线为中心，先把部署、验证、代码路径和评测入口打磨清楚，再据此推进后续的独立 runtime 设计。

## 当前状态

- 阶段：`baseline bring-up / architecture freeze`
- 基线引擎：官方 `vLLM`
- 已验证模型：`Qwen/Qwen2.5-0.5B-Instruct`
- 可选模型：`Qwen/Qwen3-8B`
- 可运行入口：[vllm_baseline/README.md](vllm_baseline/README.md)
- 运行记录：[logs/2026-04-14-vllm-bringup.md](logs/2026-04-14-vllm-bringup.md)

目前仓库的重点很直接：

- 跑通官方 `vLLM` 的 offline inference 和 online serving
- 梳理 `scheduler / prefix cache / paged attention / hybrid cache` 等关键路径
- 用一套稳定、可复现的基线流程支撑后续 C++ 模块边界设计

## 项目方向

- 目标实现语言：`C++17/20`
- 目标形态：独立的 KV Cache scheduler / runtime
- 短期工作：围绕 `vLLM` 建立可靠基线
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
bash scripts/download_model.sh qwen2_5_0_5b_instruct
bash scripts/run_offline_smoke.sh qwen2_5_0_5b_instruct
bash scripts/serve_local.sh qwen2_5_0_5b_instruct
bash scripts/verify_server.sh qwen2_5_0_5b_instruct
bash scripts/stop_server.sh qwen2_5_0_5b_instruct
```

默认验证链路使用 `Qwen/Qwen2.5-0.5B-Instruct`。`Qwen/Qwen3-8B` 作为可选预设保留，更适合更大显存机器做后续对照。

## 当前仓库包含

- `vllm_baseline/`：环境配置、模型下载、offline smoke test、local serving、API 验证
- `docs/architecture/`：未来 runtime 的模块边界与系统轮廓
- `docs/baseline/`：项目层面的 baseline 目标、约束与退出条件
- `docs/evaluation-plan.md`：基线评测计划
- `logs/`：已完成的 bring-up 记录和后续阶段日志

## 当前暂不包含

- 自研 KVFabric runtime 源码
- 面向单一框架的 patch 集
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
