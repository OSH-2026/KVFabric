# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-18_161410_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 660 | 0 | 1.0821 | 1,449.17 | +0.00% | 11.087 | 11.773 | final |
| shared_aware | 690 | 0 | 1.1431 | 1,528.50 | +5.47% | 10.481 | 11.721 | final |
| family_protect | 696 | 0 | 1.1482 | 1,535.54 | +5.96% | 10.449 | 11.746 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 2.99% | 25,872 | 2,420 | 295 | 12.1901% | +0.00% |
| shared_aware | 5.64% | 80,752 | 2,172 | 60 | 2.7624% | -79.66% |
| family_protect | 5.81% | 79,184 | 2,242 | 68 | 3.0330% | -76.95% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0.00% |
| shared_aware | 0 | 0 | 0.00% | 0.00% | 395 | 94.89% |
| family_protect | 0 | 0 | 0.00% | 0.00% | 334 | 65.88% |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 211 | 436.81 | 11.102 | 11.808 | 0 |
| shared_aware | 220 | 460.17 | 10.557 | 11.689 | 0 |
| family_protect | 220 | 458.25 | 10.535 | 11.695 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 318 | 770.06 | 11.165 | 11.777 | 0 |
| shared_aware | 329 | 804.97 | 10.741 | 11.894 | 0 |
| family_protect | 333 | 811.35 | 10.673 | 11.788 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 2 | 5.61 | 11.392 | 11.631 | 0 |
| shared_aware | 2 | 5.67 | 10.629 | 10.751 | 0 |
| family_protect | 2 | 5.64 | 9.327 | 10.624 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 129 | 236.69 | 10.868 | 11.589 | 0 |
| shared_aware | 139 | 257.69 | 9.742 | 11.356 | 0 |
| family_protect | 141 | 260.31 | 9.802 | 11.236 | 0 |

## Notes

- Best throughput policy: `family_protect` (1,535.54 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +5.47%; rebuilt delta vs LRU: -79.66%.
- `family_protect` total tok/s delta vs LRU: +5.96%; rebuilt delta vs LRU: -76.95%.
