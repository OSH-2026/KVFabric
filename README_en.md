# KVFabric

KVFabric is a KV Cache lifecycle management prototype for LLM serving. It is built on top of vLLM 0.22.1 and adds a control-plane overlay for block lifecycle metadata, prefix-family sharing signals, eviction feedback, request hints, scheduler affinity, metrics, and long-running experiment tooling.

[中文 README](README.md) | [Architecture](docs/architecture/overview.md) | [Iteration Log](docs/current/kvfabric_iteration_log.md) | [vLLM Overlay](vllm_workspace/README.md) | [Long Pressure Benchmark](experiments/long_pressure_benchmark/README.md)

![photo](docs/media/ai_photo.jpg)

## Team

- [Zhou Jiarun](https://github.com/QY-dream)
- [Zhao Tianxiang](https://github.com/ZTX1115)
- [Wang Yun](https://github.com/mjswyy)

## Current Status

As of 2026-07-01, KVFabric has a complete path from local smoke tests to remote long-running experiments:

- vLLM 0.22.1 overlay covering BlockPool, KVCacheManager, Scheduler, OpenAI serving, metrics, and experiment hooks.
- Lifecycle side table, prefix-family metadata, evicted shadow records, rebuilt-from-eviction feedback, JSONL event streams, and Prometheus metrics.
- Shared-aware eviction, family-protect trunk protection, hint-aware admission, scheduler affinity, latency guards, SLO goodput summaries, and a unified controller.
- Local Qwen3.5-2B smoke tests, remote Qwen3.5-9B experiments on a 2 x RTX 3090 server, and earlier Qwen3.5-27B exploration runs.
- Deploy / run / sync / summary / dashboard / replay tooling for reproducible long-running experiments.
- A final 12h experiment matrix covering high-pressure throughput, enterprise mixed traffic, multi-turn long conversations, low-reuse guards, and capacity sensitivity.

The current results show clear benefits in high-pressure and stable shared-prefix scenarios: fewer rebuilds after eviction, better prefix-cache quality, and improved SLO goodput near pressure boundaries. In ordinary low-frequency or low-reuse traffic, the controller keeps overhead low and avoids visible regressions in the collected runs.

## Core Components

| Component | Role |
| --- | --- |
| Lifecycle side table | Tracks block state, hash, depth, hit/share signals, recompute-cost proxy, retain score, and access time |
| Prefix Family | Groups blocks by root/parent/family metadata to describe shared trunks and branches |
| Evicted shadow | Keeps compact records of evicted blocks and detects later rebuilt-from-eviction events |
| Shared-aware eviction | Scores eviction candidates with reuse, sharing, depth, and rebuild feedback |
| Family-protect | Protects shallow shared-family trunks when pressure makes LRU evict reusable prefixes |
| Hint-aware admission | Limits cache pollution from cold or low-reuse requests while preserving durable/session reuse |
| Scheduler affinity | Promotes high-prefix-hit waiting requests with age and defer guards |
| Metrics / JSONL / dashboard | Provides lifecycle, class, segment, SLO, run-state, and replay data for debugging and reporting |

## Repository Layout

```text
KVFabric/
├─ vllm_workspace/                 # vLLM 0.22.1 overlay
├─ vllm_baseline/                  # original vLLM baseline environment
├─ experiments/
│  ├─ long_pressure_benchmark/     # remote long-running experiments and tools
│  ├─ benchmarks/                  # lifecycle policy loops
│  ├─ prebenchmark_validation/     # early local validation
│  └─ paper_reproductions/         # benchmark reproduction entries
├─ docs/
│  ├─ architecture/                # architecture documents
│  ├─ current/                     # current design and experiment notes
│  ├─ baseline/                    # baseline reading notes
│  └─ reports/                     # stage reports
└─ logs/                           # dated development logs
```

## Timeline Highlights

| Date | Progress |
| --- | --- |
| 2026-05-31 | Lifecycle probes, side table, JSONL event stream, and early vLLM control-plane hooks |
| 2026-06-07 | Long-dialogue workload, shared-aware and family-protect prototypes, local A/B validation |
| 2026-06-15 | Remote experiment planning on 2 x RTX 3090, Qwen3.5-9B / 27B selection, rerun plan |
| 2026-06-15 ~ 2026-06-22 | Metrics, realistic trace design, open-loop loadgen, remote runner, and summary tooling |
| 2026-06-22 ~ 2026-06-29 | Batch remote experiments, admission/scheduler/header fixes, run state, dashboard, replay, and final 12h matrix |
| 2026-06-30 ~ 2026-07-01 | Final report and presentation material organization |

## Main Experiment Entry

The main experiment entry is:

```text
experiments/long_pressure_benchmark/
```

Important scripts include:

- `examples/online_trace_loadgen.py`: open-loop trace replay based on `scheduled_at_seconds`.
- `examples/online_duration_loadgen.py`: duration-based mixed traffic generation.
- `scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh`: remote Qwen3.5-9B 12h matrix entry.
- `scripts/run_qwen3_5_9b_12h_matrix.sh`: in-repository Qwen3.5-9B matrix entry.
- `scripts/export_kv_cache_replay.sh`: lifecycle replay export for demos and reports.

## Documentation

- [Current iteration log](docs/current/kvfabric_iteration_log.md)
- [June iteration history](docs/current/kvfabric_june_iteration_history_2026-06-30.md)
- [Qwen3.5-9B experiment design](docs/current/kvfabric_qwen9b_experiment_design_2026-06-30.md)
- [Final code design vs vLLM](docs/current/kvfabric_final_code_design_vs_vllm_2026-06-30.md)
- [Long pressure benchmark](experiments/long_pressure_benchmark/README.md)
- [Endterm presentation slides](docs/endterm/KVFabric期末汇报.pptx)

## License

MIT
