# Remote 27B Optimization Iteration

Date: 2026-06-18

Environment:

- Host: `robowalker`
- GPU: `2 x RTX 3090 24GB`
- vLLM: `0.22.1`
- KVFabric env: `.venv_kvfabric_0221`
- Profile: `qwen3_5_27b`
- Model: `Qwen/Qwen3.5-27B-FP8`
- Workload: `experiments/prebenchmark_validation/configs/qwen3_5_27b_realistic_10h_pressure.json`

## Completed 10h Baseline

Run root:

```text
experiments/prebenchmark_validation/runs/2026-06-17_212352_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long
```

| Policy | Requests | Total tok/s | vs LRU | Avg latency s | Prefix hit | Rebuilt | Regret proxy |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| `lru` | 13,021 | 1,448.32 | baseline | 11.060 | 2.71% | 8,935 | 17.9486% |
| `shared_aware` | 14,285 | 1,589.19 | +9.73% | 10.081 | 12.97% | 60 | 0.1342% |
| `family_protect` | 14,333 | 1,594.54 | +10.10% | 10.049 | 12.98% | 68 | 0.1516% |

Conclusion: lifecycle-aware eviction is working for eviction quality, reducing
rebuilt-from-eviction by about 99%, but this workload only exposes about 13%
prefix-hit tokens under the best policy. That bounds throughput improvement well
below the 30% target unless the request mix has more durable reuse or scheduling
uses larger batches more efficiently.

## Code Changes In This Iteration

- Added head-window cache pressure snapshots in `BlockPool`.
- Added eviction-risk-aware admission fields in lifecycle events.
- Added `RequestMeta`-based cold miss defer decisions in scheduler FCFS flow.
- Added configurable cold-miss cache cap:
  - `KVFABRIC_ADMISSION_LIMIT_COLD_MISS`
  - `KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS`
  - `KVFABRIC_ADMISSION_COLD_DISCOVERY_BLOCKS`
  - `KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS`
- Wired admission into both `SingleTypeKVCacheManager.cache_blocks()` and
  `BlockPool.cache_full_blocks()`.
- Extended lifecycle and remote summaries with admission and scheduler-defer
  metrics.

## Validation Runs

### 600s Three-policy Risk Scheduler Run

Run root:

```text
experiments/prebenchmark_validation/runs/2026-06-18_161410_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long
```

| Policy | Total tok/s | vs 600s LRU | Avg latency s | Prefix hit | Rebuilt | Admission limited | Scheduler defers |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| `lru` | 1,449.17 | baseline | 11.087 | 2.99% | 295 | 0 | 0 |
| `shared_aware` | 1,528.50 | +5.48% | 10.481 | 5.64% | 60 | 0 | 395 |
| `family_protect` | 1,535.54 | +5.96% | 10.449 | 5.81% | 68 | 0 | 334 |

The scheduler defer hook worked, but admission did not trigger because the first
implementation used block counts that were too large for this 27B cache group.

### 600s Token-based Cold Cap, Anchor 1

Run root:

```text
experiments/prebenchmark_validation/runs/2026-06-18_174300_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long
```

| Policy | Total tok/s | vs 600s LRU | Avg latency s | Prefix hit | Rebuilt | Admission limited | Saved blocks | Scheduler defers |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| `family_protect` | 1,532.51 | +5.75% | 10.470 | 6.25% | 68 | 520 | 520 | 263 |

Admission now triggers and caps `cold_long` misses, but throughput does not
improve materially. This indicates cold-tail cache pollution was not the main
throughput bottleneck in the 600s window.

### 300s Seq16 / Batch-token Sweep

Run root:

```text
experiments/prebenchmark_validation/runs/2026-06-18_175728_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long
```

| Policy | Max seqs | Batched tokens | Concurrency | Total tok/s | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| `family_protect` | 16 | 16,384 | 16 | 1,523.42 | 13.995 | 15.882 |

Increasing concurrency and scheduler token budget did not raise throughput and
made latency much worse. For this server/model/workload, the earlier
`max_num_seqs=12`, `max_num_batched_tokens=8192` setting is still the better
operating point.

## Current Assessment

The 30% target is not reachable from eviction selection alone on the current
realistic mix. The durable reused prefix is one large cache block of about
784 tokens, and only about 21.6% of requests hit it in the 10h run. The best
long-run policy already preserves almost all useful reused blocks, so further
eviction tuning mostly reduces regret metrics rather than creating more reusable
work.

Most promising next changes:

1. Add request-class hints from the benchmark client to the server path, then
   use them for admission and scheduler grouping. Without class hints, hot
   family first requests are indistinguishable from one-off cold RAG misses.
2. Add explicit multi-block family lineage keyed by deeper block hashes rather
   than only the first/root hash. Current `max_family_branch_count` remains 0 or
   1 in these runs, so branch-aware protection is not yet extracting real tree
   structure.
3. Add a grouped arrival benchmark with realistic tenant burst locality. The
   current shuffled workload is deliberately hard for scheduler affinity and
   caps natural batching benefits.
4. Keep `max_num_seqs=12` and `max_num_batched_tokens=8192` for the 2x3090
   27B-FP8 environment unless a separate sweep proves otherwise.
