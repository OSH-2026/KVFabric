# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_120422_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 336 | 0 | 1.0864 | 1,448.97 | +0.00% | 11.036 | 11.836 | final |
| shared_aware | 336 | 0 | 1.1153 | 1,487.54 | +2.66% | 10.750 | 11.784 | final |
| family_protect | 348 | 0 | 1.1250 | 1,498.33 | +3.41% | 10.657 | 11.715 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 3.92% | 17,248 | 1,159 | 123 | 10.6126% | +0.00% |
| shared_aware | 5.13% | 32,928 | 1,002 | 47 | 4.6906% | -61.79% |
| family_protect | 4.93% | 32,144 | 1,098 | 56 | 5.1002% | -54.47% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 0 | 0 | 0.00% | 0.00% | 145 | 85.61% |
| family_protect | 0 | 0 | 0.00% | 0.00% | 141 | 55.80% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 336 | 100.00% | 122 | {"high": 74, "low": 161, "normal": 101} | {"durable": 74, "none": 161, "transient": 101} | {} |
| shared_aware | 336 | 100.00% | 122 | {"high": 74, "low": 161, "normal": 101} | {"durable": 74, "none": 161, "transient": 101} | {"hint_low_reuse_cold_miss": 89, "hint_transient_cold_miss": 56} |
| family_protect | 348 | 100.00% | 129 | {"high": 77, "low": 164, "normal": 107} | {"durable": 77, "none": 164, "transient": 107} | {"hint_low_reuse_cold_miss": 111, "hint_transient_cold_miss": 30} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {} | {} |
| family_protect | {} | {} |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 101 | 412.33 | 11.046 | 12.149 | 0 |
| shared_aware | 101 | 423.31 | 10.850 | 11.782 | 0 |
| family_protect | 107 | 436.74 | 10.729 | 11.715 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 161 | 768.83 | 11.077 | 11.834 | 0 |
| shared_aware | 161 | 789.29 | 10.826 | 12.526 | 0 |
| family_protect | 164 | 782.99 | 10.753 | 12.740 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 74 | 267.81 | 10.933 | 11.592 | 0 |
| shared_aware | 74 | 274.94 | 10.446 | 11.324 | 0 |
| family_protect | 77 | 278.61 | 10.354 | 11.484 | 0 |

## Notes

- Best throughput policy: `family_protect` (1,498.33 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +2.66%; rebuilt delta vs LRU: -61.79%.
- `family_protect` total tok/s delta vs LRU: +3.41%; rebuilt delta vs LRU: -54.47%.
