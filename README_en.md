# KVFabric

> KV Cache scheduling for LLM serving, with a portable C++ runtime as the long-term target

[Chinese README](README.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Baseline Workspace](vllm_baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md)

KVFabric is a systems project around KV Cache scheduling and lifecycle management for LLM serving. The repository currently centers on a reproducible `vLLM` baseline, with the baseline workflow and architecture notes living side by side.

## Status

- Stage: `baseline bring-up / architecture freeze`
- Baseline engine: upstream `vLLM`
- Verified preset: `Qwen/Qwen2.5-0.5B-Instruct`
- Optional preset: `Qwen/Qwen3-8B`
- Runnable entry point: [vllm_baseline/README.md](vllm_baseline/README.md)
- Bring-up record: [logs/2026-04-14-vllm-bringup.md](logs/2026-04-14-vllm-bringup.md)

The current focus is simple:

- bring up official `vLLM` end to end
- map the `scheduler / prefix cache / paged attention / hybrid cache` paths
- use a stable baseline to define the future C++ runtime boundaries

## Project Direction

- Implementation language: `C++17/20`
- System role: an independent KV Cache scheduler / runtime
- Short-term work: build and study a clean `vLLM` baseline
- Long-term goal: a portable scheduling design with stronger lifecycle management and clearer backend boundaries

## Planned Runtime Layout

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

## Repository Layout

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

## Quick Start

If your immediate goal is to get the baseline running, start in `vllm_baseline/`:

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

The default validated path uses `Qwen/Qwen2.5-0.5B-Instruct`. `Qwen/Qwen3-8B` remains available as an optional follow-up preset for larger GPU machines.

## What Is In This Repo

- `vllm_baseline/`: environment setup, model download, offline smoke tests, local serving, API verification
- `docs/architecture/`: runtime boundaries and design notes
- `docs/baseline/`: baseline goals, constraints, and exit criteria
- `docs/evaluation-plan.md`: evaluation plan for the baseline phase
- `logs/`: validated bring-up records and milestone notes

## What Is Not Here Yet

- custom KVFabric runtime source code
- a framework-specific patch set
- a standalone chat UI

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [vLLM Baseline](docs/baseline/README.md)
- [vLLM Baseline Workspace](vllm_baseline/README.md)
- [Evaluation Plan](docs/evaluation-plan.md)
- [Roadmap](docs/roadmap.md)
- [Research Notes](docs/research/README.md)

## License

MIT
