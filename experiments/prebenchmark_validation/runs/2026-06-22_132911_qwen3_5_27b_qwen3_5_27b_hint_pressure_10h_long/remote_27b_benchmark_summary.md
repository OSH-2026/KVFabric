# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_132911_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 8,040 | 0 | 0.6692 | 1,522.61 | +0.00% | 14.943 | 17.208 | final |
| shared_aware | 9,460 | 0 | 0.7875 | 1,791.13 | +17.64% | 12.697 | 16.346 | final |
| family_protect | 9,270 | 0 | 0.7717 | 1,754.61 | +15.24% | 12.953 | 16.344 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 5.55% | 1,017,632 | 41,200 | 11,031 | 26.7743% | +0.00% |
| shared_aware | 13.43% | 4,340,224 | 12,738 | 3,486 | 27.3669% | -68.40% |
| family_protect | 12.14% | 3,851,792 | 13,785 | 4,711 | 34.1748% | -57.29% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 4,208 | 12,643 | 100.00% | 84.04% | 4,339 | 74.55% |
| family_protect | 4,124 | 12,379 | 100.00% | 80.78% | 4,260 | 72.46% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 8,040 | 100.00% | 1,390 | {"bypass": 78, "high": 3019, "low": 3460, "normal": 1483} | {"durable": 3019, "none": 3538, "transient": 1483} | {} |
| shared_aware | 9,460 | 100.00% | 1,612 | {"bypass": 83, "high": 3559, "low": 4077, "normal": 1741} | {"durable": 3559, "none": 4160, "transient": 1741} | {"hint_bypass_cold_miss": 57, "hint_low_reuse_cold_miss": 2989, "hint_transient_cold_miss": 1293} |
| family_protect | 9,270 | 100.00% | 1,585 | {"bypass": 83, "high": 3494, "low": 3985, "normal": 1708} | {"durable": 3494, "none": 4068, "transient": 1708} | {"hint_bypass_cold_miss": 60, "hint_low_reuse_cold_miss": 2922, "hint_transient_cold_miss": 1278} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_bypass": 87, "hint_low_reuse": 4121} | {"cold_rag": 4121, "cold_rag_burst": 87} |
| family_protect | {"hint_bypass": 85, "hint_low_reuse": 4039} | {"cold_rag": 4039, "cold_rag_burst": 85} |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,483 | 261.76 | 14.897 | 16.966 | 0 |
| shared_aware | 1,741 | 307.35 | 12.842 | 16.167 | 0 |
| family_protect | 1,708 | 301.53 | 13.098 | 16.224 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 3,460 | 792.22 | 15.375 | 17.521 | 0 |
| shared_aware | 4,077 | 933.67 | 13.322 | 16.643 | 0 |
| family_protect | 3,985 | 912.60 | 13.547 | 16.648 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 78 | 21.48 | 15.736 | 18.096 | 0 |
| shared_aware | 83 | 22.87 | 13.736 | 17.081 | 0 |
| family_protect | 83 | 22.87 | 14.093 | 17.171 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 3,019 | 447.15 | 14.451 | 16.766 | 0 |
| shared_aware | 3,559 | 527.24 | 11.886 | 15.440 | 0 |
| family_protect | 3,494 | 517.61 | 12.176 | 15.616 | 0 |

## Notes

- Best throughput policy: `shared_aware` (1,791.13 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +17.64%; rebuilt delta vs LRU: -68.40%.
- `family_protect` total tok/s delta vs LRU: +15.24%; rebuilt delta vs LRU: -57.29%.
