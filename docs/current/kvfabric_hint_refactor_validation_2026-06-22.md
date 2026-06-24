# KVFabric Hint Refactor Validation - 2026-06-22

Target: vLLM 0.22.1 overlay, qwen3_5_27b / Qwen/Qwen3.5-27B-FP8 on robowalker

## Completed Remote Runs

### Realistic 2048, hint headers, pre-zero-cache

Run root:
`experiments/prebenchmark_validation/runs/2026-06-22_120422_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

Duration: 300 seconds per policy, max_model_len=2048, concurrency=12.

| Policy | Total tok/s | Delta vs LRU | Prefix hit | Rebuilt blocks | Hint coverage |
|---|---:|---:|---:|---:|---:|
| lru | 1448.97 | 0.00% | 3.92% | 123 | 100% |
| shared_aware | 1487.54 | +2.66% | 5.13% | 47 | 100% |
| family_protect | 1498.33 | +3.41% | 4.93% | 56 | 100% |

Observation: hint headers reached vLLM and scheduler deferral worked, but
admission did not save blocks because qwen3_5_27b uses a 784-token attention
block and most prompts only had one full block.

### Realistic 2048, 0-cache low-reuse admission

Run root:
`experiments/prebenchmark_validation/runs/2026-06-22_123510_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

Duration: 300 seconds per policy, max_model_len=2048, concurrency=12.

| Policy | Total tok/s | Delta vs LRU | Admission limited | Saved blocks | Rebuilt blocks |
|---|---:|---:|---:|---:|---:|
| lru | 1461.35 | 0.00% | 0 | 0 | 120 |
| shared_aware | 1510.81 | +3.39% | 42640 | 42640 | 31 |
| family_protect | 1491.25 | +2.05% | 41860 | 41860 | 52 |

Observation: 0-cache admission worked but emitted one event per repeated cache
attempt, producing tens of thousands of duplicate events and avoidable logging
overhead.

### Realistic 2048, deduplicated admission events

Run root:
`experiments/prebenchmark_validation/runs/2026-06-22_125935_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

Duration: 180 seconds per policy, max_model_len=2048, concurrency=12.

| Policy | Total tok/s | Delta vs LRU | Admission limited | Saved blocks | Rebuilt blocks |
|---|---:|---:|---:|---:|---:|
| lru | 1462.21 | 0.00% | 0 | 0 | 48 |
| shared_aware | 1476.08 | +0.95% | 92 | 92 | 12 |
| family_protect | 1466.27 | +0.28% | 92 | 92 | 28 |

Observation: event volume is fixed; the run is too short for stable throughput,
but cache-quality improvements remain visible.

### Hint-pressure 4096 smoke

Run root:
`experiments/prebenchmark_validation/runs/2026-06-22_131835_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long`

Duration: 60 seconds per policy, max_model_len=4096, concurrency=10.

| Policy | Total tok/s | Delta vs LRU | Admission limited | Saved blocks | Rebuilt blocks |
|---|---:|---:|---:|---:|---:|
| lru | 1420.92 | 0.00% | 0 | 0 | 1 |
| shared_aware | 1473.14 | +3.68% | 17 | 52 | 0 |
| family_protect | 1465.54 | +3.14% | 17 | 52 | 0 |

Observation: the 4096 configuration starts successfully and creates multi-block
requests where admission can save multiple blocks per low-reuse request.

## Active Long Run

Job:
`remote_27b_hint_pressure_10h_20260622`

PID:
`777977`

Log:
`/home/zhoujiarun/KVFabric/vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_hint_pressure_10h_20260622.log`

Run root:
`/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long`

Defaults:

- config: `qwen3_5_27b_hint_pressure_10h.json`
- max_model_len: 4096
- concurrency: 10
- max_num_seqs: 10
- max_num_batched_tokens: 16384
- policies: lru, shared_aware, family_protect
- duration: 12000 seconds per policy, approximately 10 hours total

Check status:

```bash
ssh robowalker 'cd /home/zhoujiarun/KVFabric && tail -80 vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_hint_pressure_10h_20260622.log'
```

Generate summary after completion:

```bash
ssh robowalker 'cd /home/zhoujiarun/KVFabric && .venv_kvfabric_0221/bin/python experiments/prebenchmark_validation/scripts/summarize_remote_27b_benchmark_results.py --run-root experiments/prebenchmark_validation/runs/2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long'
```

## Completed Long Run Result

The long run completed by 2026-06-24. GPU memory returned to idle
(`1 MiB / 24576 MiB` on both RTX 3090s) and no vLLM process remained.

Run root:
`experiments/prebenchmark_validation/runs/2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long`

Summary:
`experiments/prebenchmark_validation/runs/2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long/remote_27b_benchmark_summary.md`

| Policy | Requests | Total tok/s | Delta vs LRU | Avg latency | P95 latency | Prefix hit | Rebuilt blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| lru | 8040 | 1522.61 | 0.00% | 14.943s | 17.208s | 5.55% | 11031 |
| shared_aware | 9460 | 1791.13 | +17.64% | 12.697s | 16.346s | 13.43% | 3486 |
| family_protect | 9270 | 1754.61 | +15.24% | 12.953s | 16.344s | 12.14% | 4711 |

Admission and scheduler:

| Policy | Admission limited | Saved blocks | Scheduler defers | Hint coverage |
|---|---:|---:|---:|---:|
| lru | 0 | 0 | 0 | 100% |
| shared_aware | 4208 | 12643 | 4339 | 100% |
| family_protect | 4124 | 12379 | 4260 | 100% |

Class-level interpretation:

| Class | LRU tok/s | shared_aware tok/s | family_protect tok/s | Main effect |
|---|---:|---:|---:|---|
| hot_family | 447.15 | 527.24 | 517.61 | durable prefixes were retained and reused |
| cold_rag | 792.22 | 933.67 | 912.60 | low-reuse prompts were admitted as 0-cache under pressure |
| ambiguous_short_family | 261.76 | 307.35 | 301.53 | transient requests were deferred, but not cached as durable |
| cold_rag_burst | 21.48 | 22.87 | 22.87 | bypass hints avoided cold burst pollution |

Additional event analysis:

- `hot_family` prefix-hit rate from lifecycle prefix lookups:
  - LRU: about 18.72%
  - shared_aware: about 69.33%
  - family_protect: about 62.56%
- `cold_rag`, `cold_rag_burst`, and `ambiguous_short_family` had effectively
  0 prefix-hit tokens, so caching them is not useful in this workload.
- `shared_aware` outperformed `family_protect`. The hard protection path in
  `family_protect` preserved fewer hot-family hits and produced more rebuilt
  blocks than shared-aware ranking. For qwen3_5_27b on 2x3090, `shared_aware`
  should be treated as the stronger current policy.

Conclusion:

The hint-aware refactor produced a substantial real gain but did not reach the
30% target. The best policy improved total throughput by 17.64%, reduced
average latency by 15.0%, reduced p95 latency by 5.0%, and reduced rebuilt
blocks by 68.4% versus LRU. To pursue 30%, the next implementation should focus
on scheduler-positive selection for durable hot families and on reducing
family_protect over-protection, not on more low-reuse admission alone.
