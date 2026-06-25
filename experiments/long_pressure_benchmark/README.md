# Long Pressure Benchmark

This directory contains the current long-running KVFabric pressure benchmarks.
`experiments/prebenchmark_validation` is kept for early smoke tests and short
validation suites.

Design notes:

- `docs/current/kvfabric_12h_acceptance_experiment_design.md`
- `docs/current/kvfabric_30pct_throughput_refactor_research.md`

Main entry points:

- `scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh`
  starts the current 12h realistic trace benchmark on the remote 2 x RTX 3090
  server. This is the enterprise mixed trace path.
- `scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh`
  starts the closed-loop saturation benchmark. This is the main throughput
  uplift experiment and uses segmented pressure inside each 4h policy run.
- `scripts/deploy_remote_27b_long_benchmark.sh`
  syncs the overlay, configs, load generators, and long-benchmark scripts to the
  remote server.
- `scripts/status_remote_27b_benchmark.sh`
  checks remote process, GPU, job log, rolling metrics, and per-policy status.
- `scripts/sync_remote_27b_benchmark_results.sh`
  pulls summary, sampled outputs, Prometheus samples, and lifecycle metrics.

Planned formal 12h experiments:

```text
saturation_throughput_12h
enterprise_mixed_trace_12h
sticky_conversation_trace_12h
```

`saturation_throughput_12h` writes `segment_metrics.json` in addition to the
normal per-policy metrics so low-pressure guard, high-pressure main, and red
burst can be scored separately.

Raw `kvfabric_lifecycle.jsonl` streams are intentionally not included by
default. Set `INCLUDE_RAW_JSONL=1` only when a specific run needs full event
replay.
