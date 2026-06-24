# Long Pressure Benchmark

This directory contains the current long-running KVFabric pressure benchmarks.
It is separate from `experiments/prebenchmark_validation`, which is reserved for
early smoke tests and short validation suites.

Main entry points:

- `scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh`
  starts the current 12h+ realistic trace benchmark on the remote 2 x RTX 3090
  server.
- `scripts/deploy_remote_27b_long_benchmark.sh`
  syncs the overlay, configs, load generators, and long-benchmark scripts to the
  remote server.
- `scripts/status_remote_27b_benchmark.sh`
  checks remote process, GPU, job log, rolling metrics, and per-policy status.
- `scripts/sync_remote_27b_benchmark_results.sh`
  pulls summary, sampled outputs, Prometheus samples, and lifecycle metrics.

Raw `kvfabric_lifecycle.jsonl` streams are intentionally not included by
default. Set `INCLUDE_RAW_JSONL=1` only when a specific run needs full event
replay.
