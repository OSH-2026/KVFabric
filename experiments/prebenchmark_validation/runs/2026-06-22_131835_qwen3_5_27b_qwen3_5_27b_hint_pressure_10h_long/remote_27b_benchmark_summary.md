# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_131835_qwen3_5_27b_qwen3_5_27b_hint_pressure_10h_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 40 | 0 | 0.6271 | 1,420.92 | +0.00% | 15.866 | 19.207 | final |
| shared_aware | 40 | 0 | 0.6501 | 1,473.14 | +3.68% | 15.301 | 17.702 | final |
| family_protect | 40 | 0 | 0.6468 | 1,465.54 | +3.14% | 15.381 | 17.096 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 6.02% | 5,488 | 92 | 1 | 1.0870% | +0.00% |
| shared_aware | 5.11% | 5,488 | 0 | 0 | 0.0000% | -100.00% |
| family_protect | 6.02% | 5,488 | 43 | 0 | 0.0000% | -100.00% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 17 | 52 | 100.00% | 30.54% | 6 | 49.39% |
| family_protect | 17 | 52 | 100.00% | 22.54% | 0 | 0.00% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 40 | 100.00% | 20 | {"bypass": 1, "high": 16, "low": 16, "normal": 7} | {"durable": 16, "none": 17, "transient": 7} | {} |
| shared_aware | 40 | 100.00% | 20 | {"bypass": 1, "high": 16, "low": 16, "normal": 7} | {"durable": 16, "none": 17, "transient": 7} | {"hint_bypass_cold_miss": 1, "hint_low_reuse_cold_miss": 4, "hint_transient_cold_miss": 1} |
| family_protect | 40 | 100.00% | 20 | {"bypass": 1, "high": 16, "low": 16, "normal": 7} | {"durable": 16, "none": 17, "transient": 7} | {} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_bypass": 1, "hint_low_reuse": 16} | {"cold_rag": 16, "cold_rag_burst": 1} |
| family_protect | {"hint_bypass": 1, "hint_low_reuse": 16} | {"cold_rag": 16, "cold_rag_burst": 1} |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 7 | 232.74 | 14.836 | 15.761 | 0 |
| shared_aware | 7 | 241.30 | 14.404 | 15.449 | 0 |
| family_protect | 7 | 240.05 | 14.673 | 15.891 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 16 | 690.05 | 16.514 | 19.207 | 0 |
| shared_aware | 16 | 715.41 | 15.722 | 17.699 | 0 |
| family_protect | 16 | 711.72 | 15.723 | 17.096 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1 | 51.89 | 14.368 | 14.368 | 0 |
| shared_aware | 1 | 53.80 | 14.155 | 14.155 | 0 |
| family_protect | 1 | 53.52 | 14.516 | 14.516 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 16 | 446.24 | 15.762 | 19.213 | 0 |
| shared_aware | 16 | 462.64 | 15.345 | 18.842 | 0 |
| family_protect | 16 | 460.25 | 15.403 | 18.228 | 0 |

## Notes

- Best throughput policy: `shared_aware` (1,473.14 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +3.68%; rebuilt delta vs LRU: -100.00%.
- `family_protect` total tok/s delta vs LRU: +3.14%; rebuilt delta vs LRU: -100.00%.
