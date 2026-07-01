# Long Pressure Benchmark

This directory contains the remote long-running experiment suite for KVFabric. It is the main entry for Qwen3.5-9B experiments on the 2 x RTX 3090 server and also keeps earlier Qwen3.5-27B scripts for historical comparison and high-pressure exploration.

`experiments/prebenchmark_validation/` remains the entry for local smoke tests and short A/B validation.

## Related Design Notes

- `docs/current/kvfabric_qwen9b_experiment_design_2026-06-30.md`
- `docs/current/kvfabric_june_iteration_history_2026-06-30.md`
- `docs/current/kvfabric_9b_final_matrix_and_latency_iteration_2026-06-30.md`
- `docs/current/kvfabric_medium_capacity_generalization_design_2026-06-29.md`
- `docs/current/kvfabric_12h_acceptance_experiment_design.md`

## Main Qwen3.5-9B Entries

- `scripts/run_remote_qwen3_5_9b_12h_matrix_benchmark.sh`
  Starts the current remote Qwen3.5-9B 12h matrix on the 2 x RTX 3090 server. This is the preferred acceptance suite.

- `scripts/run_qwen3_5_9b_12h_matrix.sh`
  Runs the same matrix from inside a prepared repository checkout on the remote server.

- `scripts/run_qwen3_5_9b_quick_loop.sh`
  Runs shorter tuning loops for workload/SLO calibration, capacity checks, and controller parameter adjustments.

The 9B matrix is the main source for final evaluation. It covers high-pressure throughput, enterprise mixed traffic, multi-turn long-dialogue reuse, low-reuse guards, and capacity sensitivity.

## Workload and Loadgen

- `examples/online_trace_loadgen.py`
  Replays a trace in open-loop mode. Each request uses `scheduled_at_seconds`, so A/B runs share the same request plan and avoid workload drift.

- `examples/online_duration_loadgen.py`
  Generates mixed requests for a fixed duration. It is useful for quick tuning, pressure calibration, and smoke checks.

Trace fields commonly used by the 9B experiments:

```text
tenant
family
session
turn
phase
request_class
scheduled_at_seconds
expected_output_tokens / max_tokens
SLO hints
KVFabric admission/scheduler hints
```

## Final 12h Matrix

The final 12h matrix uses one KVFabric codebase and one unified controller. Stage-local presets change the emphasis of Admission, Eviction, Schedule, and SLO protect.

| Stage | Simulated scenario | Main checks |
| --- | --- | --- |
| High pressure throughput | Stable shared prefixes under capacity pressure | SLO goodput, prefix-hit tokens, rebuilt-from-eviction, segment throughput |
| Enterprise mixed traffic | Multi-tenant foreground queries, background jobs, cold RAG, session reuse | class latency, foreground protection, admission behavior |
| Multi-turn long dialogue | Long sessions with growing shared trunks and branch turns | family-protect, scheduler affinity, lifecycle family signals |
| Low-reuse guard | Low-frequency, decode-heavy, cold or low-reuse traffic | overhead, tail latency, non-regression |

## Remote Tooling

- `scripts/deploy_remote_27b_long_benchmark.sh`
  Historical deployment script name. It syncs overlay, configs, load generators, and benchmark scripts to the remote host. It is still useful for the shared remote workflow.

- `scripts/status_remote_27b_benchmark.sh`
  Checks remote process, GPU status, job logs, rolling metrics, and per-policy run state.

- `scripts/sync_remote_27b_benchmark_results.sh`
  Pulls summaries, sampled outputs, Prometheus samples, lifecycle metrics, and selected artifacts.

- `scripts/run_remote_27b_dashboard.sh`
  Starts the Streamlit dashboard on the remote server. Use `ssh -L 8501:127.0.0.1:8501 robowalker` and open `http://127.0.0.1:8501` locally. If dependencies cannot be installed, the script falls back to a static HTML dashboard.

- `scripts/export_kv_cache_replay.sh`
  Renders a replay artifact from a policy's `kvfabric_lifecycle.jsonl` for debugging and report demos.

Some remote scripts still contain `27b` in their names because they were introduced during the first remote long-pressure phase. Their current role is broader than the original name.

## Historical 27B Entries

These scripts are retained for reference and reruns:

- `scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh`
- `scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh`
- `scripts/run_remote_27b_sticky_conversation_trace_12h_benchmark.sh`
- `scripts/run_remote_27b_saturation_throughput_4h_benchmark.sh`
- `scripts/run_remote_27b_enterprise_mixed_trace_4h_benchmark.sh`
- `scripts/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh`
- `scripts/run_remote_27b_4h_benchmark_suite.sh`
- `scripts/start_remote_27b_sticky_with_dashboard.sh`
- `scripts/start_remote_27b_4h_suite_with_dashboard.sh`

## Artifacts

Formal runs should keep:

- run config and environment;
- trace file or trace generation parameters;
- loadgen output;
- server log;
- lifecycle summary;
- Prometheus or sampled metrics;
- SLO goodput summary;
- run state and heartbeat;
- selected dashboard/replay screenshots when used in reports.

Raw `kvfabric_lifecycle.jsonl` streams can be large. Set `INCLUDE_RAW_JSONL=1` only when full event replay is needed.
