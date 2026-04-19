# KVFabric

> KV Cache scheduling for LLM serving, with a vLLM Python-control-plane prototype first and a portable C++ runtime as the long-term target

[Chinese README](README.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Baseline Workspace](vllm_baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md)

KVFabric is a systems project around KV Cache scheduling and lifecycle management for LLM serving. The repository currently centers on a `vLLM` baseline: first we make the deployment flow, validation path, key code paths, and evaluation entry points clear and reproducible. If we need to modify `vLLM` source code in the short term to validate unified lifecycle management, sharing-aware eviction, or post-sharing branching, the current boundary is Python control-plane first rather than starting with C++/CUDA kernels.

## Team Members

- [Zhou Jiarun](https://github.com/QY-dream)
- [Zhao Tianxiang](https://github.com/ZTX1115)
- [Wang Yun](https://github.com/mjswyy)

---

| Project Stage | Date | Progress | Task Breakdown | Outcome | Appendix |
|:---------------------------:|:---------:|:-------------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:-----------------:| ----------------------------------- |
| Personal Topic Research | 2026-03-23 | Online group meeting to exchange individual topic ideas | Reviewed currently feasible topic directions and discussed their practicality | Decided that each member would conduct individual topic research after the meeting, then align in a follow-up group discussion to form an initial topic direction | [log](logs/2026-03-23.md) |
| Topic Selection | 2026-03-28 | Offline meeting to discuss candidate topics and identify a project direction | Zhou Jiarun: a simple eBPF-based KV Cache profiler for AIOS/vLLM and bottleneck analysis; Zhao Tianxiang: a runnable validation OS for a self-developed loong arch CPU, [research note](docs/research/individual_research/ZhaoTianxiang/ztx_research1.md); Wang Yun: rewrite a simple OS in Rust | Decided to use the loong arch validation OS topic | [log](logs/2026-03-28.md) |
| Topic Selection | 2026-03-28 | Online meeting | Reported topic to the instructor and asked for feedback | Topic was rejected and needed to be revised | |
| Topic Selection | 2026-03-29 | Individual research and online group discussion | Zhou Jiarun: [research note](docs/research/individual_research/ZhouJiarun/zjr_research.md), topic: unified KV Cache lifecycle management + chunk-level reuse + CoW branching; Zhao Tianxiang: [research note](docs/research/individual_research/ZhaoTianxiang/ztx_research2.md), topic: coordinated KV Cache allocation, reuse, and eviction for LLM serving; Wang Yun: [research note](docs/research/individual_research/WangYun/wy_research.md), topic: lightweight AI user-space scheduling engine design for mobile devices | Final topic selected: "unified KV Cache lifecycle management + chunk-level reuse + CoW branching" | [log](logs/2026-03-29.md) |
| Topic Selection | 2026-03-29 | Online meeting | Reported revised topic to the instructor and asked for feedback | Topic approved | |
| Learning | 2026-04-07 | Studied LLM inference and KV Cache analysis; selected implementation platform | Zhou Jiarun: [LLM inference and KV Cache analysis](docs/research/group_research/investigation.pdf); Zhao Tianxiang: [vLLM and llama.cpp suitability study](docs/research/individual_research/ZhaoTianxiang/ztx_research3.md); Wang Yun: [vLLM vs llama.cpp comparison](docs/research/group_research/vllm-vs-llamacpp.md) | Completed initial study and decided to implement on vLLM | [log](logs/2026-04-07.md) |
| Project Setup | 2026-04-13 | Brought up the vLLM baseline environment and validated the inference path | Zhou Jiarun: environment setup, inference pipeline bring-up, and initial performance collection; Zhao Tianxiang: feasibility report; Wang Yun: logs and documentation | Successfully brought up the vLLM environment, validated the end-to-end inference path, and collected initial performance data | [log](logs/2026-04-14-vllm-bringup.md) |
| Group Discussion | 2026-04-19 | Offline discussion on follow-up direction and planning | Discussed the follow-up vLLM modification scope and design approach, and clarified next-step tasks | Before next Wednesday, complete vLLM source reading and KV Cache call-chain analysis, then hold a meeting next Wednesday to finalize detailed task splitting | [log](logs/2026-04-19.md) |

---

## Status

- Stage: `baseline bring-up / architecture freeze`
- Baseline engine: upstream `vLLM`
- Verified preset: `Qwen/Qwen2.5-0.5B-Instruct`
- Optional preset: `Qwen/Qwen3-8B`
- Runnable entry point: [vllm_baseline/README.md](vllm_baseline/README.md)
- Bring-up record: [logs/2026-04-14-vllm-bringup.md](logs/2026-04-14-vllm-bringup.md)

The current focus is straightforward:

- run official `vLLM` for both offline inference and online serving
- map the `scheduler / prefix cache / paged attention / hybrid cache` paths
- identify the short-term `vLLM` prototype scope in Python scheduler, KV cache manager, block pool, and metadata paths
- use a stable and reproducible baseline workflow to support the later C++ module boundary design

## Project Direction

- Short-term implementation boundary: if we patch `vLLM`, start with Python control-plane files such as `vllm/v1/core/sched/`, `vllm/v1/core/kv_cache_manager.py`, `vllm/v1/core/block_pool.py`, `vllm/v1/core/kv_cache_utils.py`, and `vllm/v1/core/single_type_kv_cache_manager.py`
- Not the first target: C++/CUDA attention kernels, low-level KV physical layout, or custom ops, unless a later feature must change block memory layout, slot-mapping semantics, or kernel write/copy paths
- Long-term implementation language: `C++17/20`
- Long-term system role: an independent KV Cache scheduler / runtime
- Long-term goal: an independently evolving systems design around portability, scheduler design, and lifecycle management

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

The default validated path uses `Qwen/Qwen2.5-0.5B-Instruct`. `Qwen/Qwen3-8B` remains available as an optional preset for follow-up comparisons on machines with larger GPU memory.

## What Is In This Repo

- `vllm_baseline/`: environment setup, model download, offline smoke tests, local serving, API verification
- `docs/architecture/`: runtime boundaries and design notes
- `docs/baseline/`: baseline goals, constraints, and exit criteria
- `docs/evaluation-plan.md`: evaluation plan for the baseline phase
- `logs/`: validated bring-up records and milestone notes

## What Is Not Here Yet

- custom KVFabric runtime source code
- an implemented `vLLM` patch set
- C++/CUDA kernel changes
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
