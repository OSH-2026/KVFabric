# KVFabric

> A vLLM Python-control-plane prototype for KVCache lifecycle management, sharing-aware eviction, and long-dialogue stress testing.

[Chinese README](README.md) | [Architecture](docs/architecture/overview.md) | [Current Iteration Log](docs/current/kvfabric_iteration_log.md) | [vLLM Overlay](vllm_workspace/README.md) | [Long Pressure Benchmark](experiments/long_pressure_benchmark/README.md) | [12h Acceptance Design](docs/current/kvfabric_12h_acceptance_experiment_design.md) | [Research Report](docs/research/group_research/research_report.md) | [Feasibility Report](docs/reports/feasibility_report.md)

KVFabric is a systems project for KVCache lifecycle management in LLM serving. The current implementation is no longer only a baseline workspace: it now contains a runnable vLLM Python-control-plane prototype with lifecycle instrumentation, event logging, metrics probes, sharing-aware policies, A/B scripts, and long-dialogue workload generation.

The core idea is to treat KV blocks as managed lifecycle objects rather than passive cache pages. On top of vLLM prefix caching, KVFabric tracks block state, sharing signals, prefix depth, reuse history, eviction quality, and rebuild-after-eviction behavior. These signals are then used to distinguish reusable shared-prefix blocks from low-value private tails under KV pressure.

## Team

- [Zhou Jiarun](https://github.com/QY-dream)
- [Zhao Tianxiang](https://github.com/ZTX1115)
- [Wang Yun](https://github.com/mjswyy)

## Current Status

Completed work includes:

- vLLM baseline validation for offline inference, OpenAI-compatible serving, and metrics collection.
- Lifecycle probes and side-table encapsulation for allocation, sealed blocks, prefix hits, ref-count changes, evictions, and rebuild-after-eviction events.
- vLLM overlay support for `shared_aware`, `family_protect`, hint-aware admission/scheduler hooks, JSONL lifecycle logs, and Prometheus metrics.
- A/B validation scripts in `experiments/prebenchmark_validation/` and 27B long-pressure automation in `experiments/long_pressure_benchmark/`.
- Long-dialogue stress testing in `experiments/langtime_running_test/`.
- Initial validation showing low overhead in ordinary no-sharing workloads and better eviction quality in template-like / multi-turn reuse workloads.

Current conclusion:

- In ordinary no-sharing workloads, KVFabric mostly falls back to a low-overhead path.
- In template prompts, similar multi-turn conversations, and repeated prefix-family workloads, KVFabric can reduce shared-anchor eviction and rebuilt-from-eviction events.
- The current prototype is best described as an explainable KVCache resource-management prototype, not a universal throughput accelerator.

## Core Design

### Lifecycle Side Table

KVFabric maintains a side table for KV block metadata:

- block id and block hash;
- prefix depth and recompute-cost proxy;
- ref count, hit count, share degree, branch-factor proxy;
- lifecycle state;
- retain score;
- rebuilt-from-eviction information.

The side table is observational and policy-oriented. It does not change vLLM worker-side block table semantics or attention execution behavior.

### Shared Prefix Protection

vLLM prefix caching reuses strict full-block common prefixes. KVFabric builds on that by distinguishing:

- shared-prefix anchors that are likely to be reused;
- private tail blocks that are unlikely to be reused;
- ambiguous cold/hot candidates under KV pressure.

The current `family_protect` policy keeps vLLM's free-queue order but defers protected shared-family blocks when possible.

### Policies

Current policy modes:

- `lru`: lifecycle logging only, preserving vLLM behavior.
- `shared_aware`: retain-score ranking over eviction candidates.
- `family_protect`: lightweight protected-block deferral for reusable prefix families.

Common environment variables:

```bash
KVFABRIC_LIFECYCLE=1
KVFABRIC_LIFECYCLE_LOG_PATH=/path/to/kvfabric_lifecycle.jsonl
KVFABRIC_EVICTION_POLICY=lru|shared_aware|family_protect
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24
```

## Repository Layout

```text
KVFabric/
├─ vllm_baseline/                         # vLLM baseline service and metrics scripts
├─ vllm_workspace/                        # vLLM Python-control-plane overlay
├─ experiments/
│  ├─ prebenchmark_validation/            # early online validation, lifecycle logs, A/B reports
│  ├─ long_pressure_benchmark/            # current remote 27B long-pressure suites
│  ├─ benchmarks/lifecycle_policy/         # deterministic Python lifecycle-policy loop
│  ├─ langtime_running_test/               # long-dialogue and multi-turn stress tests
│  └─ paper_reproductions/                 # performance and quality benchmark workflows
├─ docs/
│  ├─ current/                             # current plans, iteration log, handoff notes
│  ├─ architecture/                        # current architecture overview
│  ├─ reports/                             # feasibility and benchmark reports
│  └─ research/                            # research notes
└─ logs/                                   # group discussion and implementation logs
```

## Validation

Representative A/B workloads:

- `ordinary_unique_cold.json`: ordinary no-sharing sanity check.
- `template_family_revisit.json`: single-cycle template-family revisit.
- `template_family_revisit_cycles.json`: multi-cycle template-family revisit.
- `cache_pressure_ambiguous_hot_revisit.json`: ambiguous hot/cold pressure test.

Important outputs:

- lifecycle JSONL events;
- `kvfabric_lifecycle_metrics.json`;
- Prometheus metrics summary;
- online request metrics;
- `ab_comparison.md`.

## Documentation

- [Current Iteration Log](docs/current/kvfabric_iteration_log.md)
- [Source Modification and Team Plan](docs/current/source_modification_and_team_plan.md)
- [3090 Handoff](docs/current/3090_handoff.md)
- [12h Acceptance Experiment Design](docs/current/kvfabric_12h_acceptance_experiment_design.md)
- [30% Throughput Refactor Research](docs/current/kvfabric_30pct_throughput_refactor_research.md)
- [Long Pressure Benchmark](experiments/long_pressure_benchmark/README.md)
- [vLLM Overlay Workspace](vllm_workspace/README.md)
- [Prebenchmark Validation](experiments/prebenchmark_validation/README.md)
- [Lifecycle Policy Loop](experiments/benchmarks/lifecycle_policy/README.md)
- [Long Dialogue Stress Test](experiments/langtime_running_test/README.md)
- [Feasibility Report](docs/reports/feasibility_report.md)

## License

MIT
