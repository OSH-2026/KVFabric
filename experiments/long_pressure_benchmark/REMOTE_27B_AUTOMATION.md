# Remote 27B Benchmark Automation

This note is the recovery point for the long `qwen3_5_27b` benchmark on
`robowalker`.

## Defaults

- Remote host: `robowalker`
- Remote project: `/home/zhoujiarun/KVFabric`
- Remote venv: `.venv_kvfabric_0221`
- Profile: `qwen3_5_27b`
- Model: `Qwen/Qwen3.5-27B-FP8`
- Config: `experiments/long_pressure_benchmark/configs/qwen3_5_27b_realistic_10h_pressure.json`
- Policies: `lru shared_aware family_protect`
- Duration: `12000` seconds per policy, about 10 hours total with restarts
- Concurrency: `12`
- Serve caps: `LONG_BENCH_MAX_NUM_SEQS=12`,
  `LONG_BENCH_MAX_NUM_BATCHED_TOKENS=8192`

## Deploy Code To Remote

Use this before starting a new remote run when local scripts or overlay code
changed:

```bash
REMOTE_MODE=sync \
bash experiments/long_pressure_benchmark/scripts/deploy_remote_27b_long_benchmark.sh
```

## Start A New 10h Remote Job

The launcher writes a remote job script, log, and pid file under
`vllm_baseline/runtime_kvfabric_0221/jobs/`.

```bash
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_realistic_10h_benchmark.sh
```

Useful overrides:

```bash
LONG_BENCH_DURATION_SECONDS=12000 \
LONG_BENCH_CONCURRENCY=12 \
LONG_BENCH_MAX_NUM_SEQS=12 \
LONG_BENCH_MAX_NUM_BATCHED_TOKENS=8192 \
bash experiments/long_pressure_benchmark/scripts/run_remote_27b_realistic_10h_benchmark.sh
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

Full sync including large lifecycle JSONL files, recommended after completion:

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
