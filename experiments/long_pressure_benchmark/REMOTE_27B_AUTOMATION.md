# Remote 27B Benchmark Automation

This note is the recovery point for long `qwen3_5_27b` benchmarks on
`robowalker`. Current long runs live under `experiments/long_pressure_benchmark`.

## Defaults

- Remote host: `robowalker`
- Remote project: `/home/zhoujiarun/KVFabric`
- Remote venv: `.venv_kvfabric_0221`
- Profile: `qwen3_5_27b`
- Model: `Qwen/Qwen3.5-27B-FP8`
- Default config:
  `experiments/long_pressure_benchmark/configs/qwen3_5_27b_enterprise_mixed_trace_12h.json`
- Saturation config:
  `experiments/long_pressure_benchmark/configs/qwen3_5_27b_saturation_throughput_12h.json`
- Sticky conversation config:
  `experiments/long_pressure_benchmark/configs/qwen3_5_27b_sticky_conversation_trace_12h.json`
- Policies: `lru shared_aware family_protect`
- Formal duration: 4 hours per policy, 12 hours total
- Short-run duration: 80 minutes per policy, 4 hours total
- Current pressure target: calibrate LRU into ORANGE pressure before a formal run
- Serve caps to start calibration:
  `LONG_BENCH_MAX_NUM_SEQS=16`,
  `LONG_BENCH_MAX_NUM_BATCHED_TOKENS=16384`

Formal experiment design:

```text
docs/current/kvfabric_12h_acceptance_experiment_design.md
docs/current/kvfabric_30pct_throughput_refactor_research.md
```

## Deploy Code To Remote

Use this before starting a new remote run when local scripts or overlay code
changed:

```bash
REMOTE_MODE=sync \
bash experiments/long_pressure_benchmark/scripts/deploy_remote_27b_long_benchmark.sh
```

## Start A New 12h Enterprise Trace Job

The launcher writes a remote job script, log, and pid file under
`vllm_baseline/runtime_kvfabric_0221/jobs/`.

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh
```

Useful overrides:

```bash
LONG_BENCH_MAX_NUM_SEQS=16 \
LONG_BENCH_MAX_NUM_BATCHED_TOKENS=16384 \
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_12h_benchmark.sh
```

The older `run_remote_27b_realistic_10h_benchmark.sh` and
`run_remote_27b_hint_pressure_10h_benchmark.sh` launchers are kept for result
reproduction.

## Start A New 12h Saturation Job

This is the main high-pressure throughput experiment.

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh
```

Useful overrides:

```bash
LONG_BENCH_MAX_NUM_SEQS=20 \
LONG_BENCH_MAX_NUM_BATCHED_TOKENS=16384 \
KVFABRIC_SCHEDULER_AFFINITY=positive \
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_saturation_throughput_12h_benchmark.sh
```

## Start A New 12h Sticky Conversation Job

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_sticky_conversation_trace_12h_benchmark.sh
```

## Start Short 4h Jobs

These launch the same three-policy A/B structure as the formal suites, but each
policy runs for 80 minutes.

Run all missing 4h suites in order:

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_4h_benchmark_suite.sh
```

Or start one suite directly:

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_saturation_throughput_4h_benchmark.sh
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_enterprise_mixed_trace_4h_benchmark.sh
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_sticky_conversation_trace_4h_benchmark.sh
```

## Check Progress

```bash
bash experiments/long_pressure_benchmark/scripts/status_remote_27b_benchmark.sh
```

The status script prints the latest matched run root, remote job log tail,
GPU state, active processes, per-policy metrics, class metrics, and run size.

For a specific run:

```bash
REMOTE_RUN_ROOT=experiments/long_pressure_benchmark/runs/<run-dir> \
bash experiments/long_pressure_benchmark/scripts/status_remote_27b_benchmark.sh
```

## Sync Results And Build Summary

Summary-only sync, recommended during an active run:

```bash
bash experiments/long_pressure_benchmark/scripts/sync_remote_27b_benchmark_results.sh
```

Full sync including large lifecycle JSONL files, use only for targeted replay:

```bash
INCLUDE_RAW_JSONL=1 \
bash experiments/long_pressure_benchmark/scripts/sync_remote_27b_benchmark_results.sh
```

The sync script writes:

```text
experiments/long_pressure_benchmark/runs/<run-dir>/remote_27b_benchmark_summary.md
```

To regenerate a summary from an already synced run:

```bash
python experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py \
  --run-root experiments/long_pressure_benchmark/runs/<run-dir>
```

## Historical 2026-06-17 Long Run

The original 2026-06-17 formal run was started from this job:

```text
vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_realistic_10h.sh
vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_realistic_10h.log
vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_realistic_10h.pid
```

That historical run root remains under `prebenchmark_validation` because old
results are not moved during the benchmark-layout cleanup:

```text
experiments/prebenchmark_validation/runs/2026-06-17_212352_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long
```

New long benchmark runs are written under:

```text
experiments/long_pressure_benchmark/runs/
```

If a long run is interrupted, first run the status script. If all policies are
complete, run the full sync command and inspect the generated summary.
