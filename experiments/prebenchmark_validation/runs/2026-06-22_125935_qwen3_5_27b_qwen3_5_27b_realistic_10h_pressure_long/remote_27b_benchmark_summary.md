# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-22_125935_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 204 | 0 | 1.1025 | 1,462.21 | +0.00% | 10.869 | 11.420 | final |
| shared_aware | 204 | 0 | 1.1130 | 1,476.08 | +0.95% | 10.766 | 12.646 | final |
| family_protect | 204 | 0 | 1.1056 | 1,466.27 | +0.28% | 10.838 | 12.625 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 4.69% | 12,544 | 662 | 48 | 7.2508% | +0.00% |
| shared_aware | 5.06% | 18,032 | 195 | 12 | 6.1538% | -75.00% |
| family_protect | 5.80% | 15,680 | 286 | 28 | 9.7902% | -41.67% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 92 | 92 | 100.00% | 62.31% | 67 | 73.30% |
| family_protect | 92 | 92 | 100.00% | 28.26% | 1 | 45.23% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 204 | 100.00% | 87 | {"high": 47, "low": 92, "normal": 65} | {"durable": 47, "none": 92, "transient": 65} | {} |
| shared_aware | 204 | 100.00% | 87 | {"high": 47, "low": 92, "normal": 65} | {"durable": 47, "none": 92, "transient": 65} | {"hint_low_reuse_cold_miss": 42, "hint_transient_cold_miss": 25} |
| family_protect | 204 | 100.00% | 87 | {"high": 47, "low": 92, "normal": 65} | {"durable": 47, "none": 92, "transient": 65} | {"hint_low_reuse_cold_miss": 1} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_low_reuse": 92} | {"cold_rag": 92} |
| family_protect | {"hint_low_reuse": 92} | {"cold_rag": 92} |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 65 | 443.53 | 10.882 | 11.973 | 0 |
| shared_aware | 65 | 447.74 | 10.780 | 11.654 | 0 |
| family_protect | 65 | 444.76 | 10.798 | 11.628 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 92 | 734.36 | 10.918 | 11.232 | 0 |
| shared_aware | 92 | 741.32 | 10.876 | 12.647 | 0 |
| family_protect | 92 | 736.40 | 10.959 | 12.635 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 47 | 284.32 | 10.753 | 11.136 | 0 |
| shared_aware | 47 | 287.02 | 10.532 | 11.612 | 0 |
| family_protect | 47 | 285.11 | 10.656 | 11.622 | 0 |

## Notes

- Best throughput policy: `shared_aware` (1,476.08 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +0.95%; rebuilt delta vs LRU: -75.00%.
- `family_protect` total tok/s delta vs LRU: +0.28%; rebuilt delta vs LRU: -41.67%.
