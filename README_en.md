# KVFabric

> A portable, C++-first KV Cache scheduling project for LLM serving systems

[Chinese README](README.md) | [Architecture](docs/architecture/overview.md) | [vLLM Baseline](docs/baseline/README.md) | [Research Notes](docs/research/README.md) | [Roadmap](docs/roadmap.md)

## About

KVFabric is a KV Cache scheduling project for LLM serving systems. The long-term goal is not to add a few policies on top of an existing Python stack, but to build a **portable, independently evolvable, C++-first** scheduler and lifecycle manager for KV Cache.

The project is intended to go beyond vLLM's default behavior in portability, scheduler expressiveness, and lifecycle management, while remaining grounded in practical serving workloads.

## Current Stage

The repository is currently in the **baseline bring-up / architecture freeze** stage. That means the immediate goal is **not** to write custom scheduler code yet. Instead, the project first needs to deploy, run, and understand upstream `vLLM` locally or on an equivalent Linux environment.

Current work is focused on:

- deploying and validating official `vLLM`
- running minimal offline and online serving tests
- understanding `scheduler / prefix cache / paged attention / hybrid cache` paths
- documenting bottlenecks and architectural constraints
- freezing the module boundaries for the future C++ implementation

For that reason, this repository intentionally does **not** keep an early custom runtime implementation at this stage.

## Direction

- **Implementation language**: primarily `C++17/20`
- **System role**: an independent KV Cache scheduler / runtime
- **Short-term baseline**: official `vLLM`
- **Long-term target**: a more portable and capable KV Cache scheduling design than the default vLLM path

## Repository Layout

```text
KVFabric/
├─ .github/
├─ docs/
│  ├─ architecture/
│  ├─ baseline/
│  ├─ media/
│  ├─ reports/
│  └─ research/
└─ logs/
```

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [vLLM Baseline Plan](docs/baseline/README.md)
- [Evaluation Plan](docs/evaluation-plan.md)
- [Roadmap](docs/roadmap.md)
- [Research Notes](docs/research/README.md)

## License

MIT
