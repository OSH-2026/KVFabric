# Long Pressure Benchmark

This directory contains the current long-running KVFabric pressure benchmarks.
`experiments/prebenchmark_validation` is kept for early smoke tests and short
validation suites.

Design notes:

- `docs/current/kvfabric_12h_acceptance_experiment_design.md`
- `docs/current/kvfabric_30pct_throughput_refactor_research.md`
- `docs/current/kvfabric_medium_capacity_generalization_design_2026-06-29.md`

Main entry points:

- `scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh`
  starts the current Qwen3.5-9B medium-capacity matrix on the remote 2 x RTX
  3090 server. This is the preferred next-round suite for proving high-pressure
  SLO goodput, suitable-scenario e2e latency improvement, capacity sensitivity,
  and low-reuse non-regression within roughly 12 hours.
- `scripts/run_qwen3_5_9b_12h_matrix.sh`
  runs the same Qwen3.5-9B matrix from inside a prepared repository checkout,
  useful when already logged in to the remote server.
- `scripts/run_qwen3_5_9b_quick_loop.sh`
  runs the short daily-dedicated tuning loop, defaulting to medium and small KV
  capacity profiles.
- `scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh`
  starts the current 12h realistic trace benchmark on the remote 2 x RTX 3090
  server. This is the enterprise mixed trace path.
- `scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh`
  starts the closed-loop saturation benchmark. This is the main throughput
  uplift experiment and uses segmented pressure inside each 4h policy run.
- `scripts/run_remote_27b_sticky_conversation_trace_12h_benchmark.sh`
  starts the sticky multi-turn conversation trace benchmark.
- `scripts/run_remote_27b_saturation_throughput_4h_benchmark.sh`,
  `scripts/run_remote_27b_enterprise_mixed_trace_4h_benchmark.sh`, and
  `scripts/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh`
  start short acceptance runs. These keep the same workload mix and pressure
  settings as the formal suites, but reduce each policy run to 80 minutes so
  the three-policy A/B finishes in roughly 4 hours.
- `scripts/run_remote_27b_4h_benchmark_suite.sh`
  starts the three short suites in order and skips suites that already have a
  remote run directory by default.
- `scripts/deploy_remote_27b_long_benchmark.sh`
  syncs the overlay, configs, load generators, and long-benchmark scripts to the
  remote server.
- `scripts/status_remote_27b_benchmark.sh`
  checks remote process, GPU, job log, rolling metrics, and per-policy status.
- `scripts/sync_remote_27b_benchmark_results.sh`
  pulls summary, sampled outputs, Prometheus samples, and lifecycle metrics.
- `scripts/run_remote_27b_dashboard.sh`
  starts the Streamlit dashboard on the remote server. Use
  `ssh -L 8501:127.0.0.1:8501 robowalker` and open
  `http://127.0.0.1:8501` locally. It installs
  `dashboard/requirements.txt` into the remote benchmark venv by default. If the
  remote host cannot install Python packages, it falls back to a dependency-free
  HTML dashboard backed by `run_kvfabric_dashboard_static.py`.
- `scripts/start_remote_27b_sticky_with_dashboard.sh`
  starts the Sticky 4h benchmark and then opens the dashboard for the new run.
- `scripts/start_remote_27b_4h_suite_with_dashboard.sh`
  starts the three 4h experiments in sequence with `KVFABRIC_4H_SUITE_SKIP_EXISTING=0`
  by default and opens a dashboard that follows the newest run directory.
- `scripts/export_kv_cache_replay.sh`
  renders a GIF from a policy's `kvfabric_lifecycle.jsonl` for report demos.

Planned formal 12h experiments:

```text
qwen3_5_9b_12h_matrix
saturation_throughput_12h
enterprise_mixed_trace_12h
sticky_conversation_trace_12h
```

Qwen3.5-9B matrix modules:

```text
capacity_sweep_6m
daily_dedicated_reuse_40m
saturation_medium_60m
sticky_burst_45m
enterprise_normal_25m
low_reuse_low_frequency_20m
```

Short 4h mirrors:

```text
saturation_throughput_4h
enterprise_mixed_trace_4h
sticky_conversation_trace_4h
```

`saturation_throughput_12h` writes `segment_metrics.json` in addition to the
normal per-policy metrics so low-pressure guard, high-pressure main, and red
burst can be scored separately.

Raw `kvfabric_lifecycle.jsonl` streams are intentionally not included by
default. Set `INCLUDE_RAW_JSONL=1` only when a specific run needs full event
replay.
