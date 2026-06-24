# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_123510_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 336 | 0 | 1.0957 | 1,461.35 | +0.00% | 10.943 | 11.658 | final |
| shared_aware | 348 | 0 | 1.1343 | 1,510.81 | +3.39% | 10.569 | 11.743 | final |
| family_protect | 336 | 0 | 1.1181 | 1,491.25 | +2.05% | 10.719 | 11.898 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 4.09% | 18,032 | 1,155 | 120 | 10.3896% | +0.00% |
| shared_aware | 5.68% | 36,848 | 373 | 31 | 8.3110% | -74.17% |
| family_protect | 6.96% | 32,144 | 455 | 52 | 11.4286% | -56.67% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 42,640 | 42,640 | 100.00% | 80.14% | 143 | 75.46% |
| family_protect | 41,860 | 41,860 | 100.00% | 40.25% | 11 | 47.62% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 336 | 100.00% | 122 | {"high": 74, "low": 161, "normal": 101} | {"durable": 74, "none": 161, "transient": 101} | {} |
| shared_aware | 348 | 100.00% | 129 | {"high": 77, "low": 164, "normal": 107} | {"durable": 77, "none": 164, "transient": 107} | {"hint_low_reuse_cold_miss": 84, "hint_transient_cold_miss": 59} |
| family_protect | 336 | 100.00% | 122 | {"high": 74, "low": 161, "normal": 101} | {"durable": 74, "none": 161, "transient": 101} | {"hint_low_reuse_cold_miss": 11} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_low_reuse": 42640} | {"cold_rag": 42640} |
| family_protect | {"hint_low_reuse": 41860} | {"cold_rag": 41860} |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 101 | 415.85 | 10.980 | 12.242 | 0 |
| shared_aware | 107 | 440.38 | 10.675 | 11.743 | 0 |
| family_protect | 101 | 424.36 | 10.820 | 11.896 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 161 | 775.39 | 10.997 | 11.658 | 0 |
| shared_aware | 164 | 789.51 | 10.658 | 12.592 | 0 |
| family_protect | 161 | 791.26 | 10.793 | 12.637 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 74 | 270.10 | 10.775 | 11.427 | 0 |
| shared_aware | 77 | 280.93 | 10.234 | 11.241 | 0 |
| family_protect | 74 | 275.63 | 10.422 | 11.194 | 0 |

## Notes

- Best throughput policy: `shared_aware` (1,510.81 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +3.39%; rebuilt delta vs LRU: -74.17%.
- `family_protect` total tok/s delta vs LRU: +2.05%; rebuilt delta vs LRU: -56.67%.
