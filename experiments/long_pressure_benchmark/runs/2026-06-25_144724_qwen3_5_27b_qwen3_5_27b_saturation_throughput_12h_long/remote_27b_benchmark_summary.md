# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-25_144724_qwen3_5_27b_qwen3_5_27b_saturation_throughput_12h_long`

## Throughput And Latency

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | Total tok/s | Goodput vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 7,928 | 0 | n/a | 0.5501 | 601.57 | 1,424.99 | +0.00% | 27.264 | 33.662 | final |
| shared_aware | 8,066 | 0 | n/a | 0.5596 | 675.80 | 1,449.70 | +12.34% | 26.791 | 33.137 | final |
| family_protect | 7,894 | 0 | n/a | 0.5477 | 572.13 | 1,418.73 | -4.89% | 27.383 | 34.104 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 1.79% | 357,504 | 43,161 | 12,680 | 29.3784% | +0.00% |
| shared_aware | 2.94% | 702,464 | 12,328 | 3,566 | 28.9260% | -71.88% |
| family_protect | 0.96% | 224,224 | 12,221 | 3,966 | 32.4523% | -68.72% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Scheduler promotes | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0.00% |
| shared_aware | 6,447 | 14,501 | 80.63% | 90.34% | 1,516 | 1,746 | 83.71% |
| family_protect | 6,601 | 14,758 | 79.92% | 89.38% | 1,472 | 1,651 | 81.99% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 7,928 | 100.00% | 1,291 | {"bypass": 314, "high": 4132, "low": 2614, "normal": 868} | {"durable": 4132, "none": 2928, "transient": 868} | {} |
| shared_aware | 8,066 | 100.00% | 1,303 | {"bypass": 317, "high": 4201, "low": 2668, "normal": 880} | {"durable": 4201, "none": 2985, "transient": 880} | {"hint_bypass_cold_miss": 112, "hint_low_reuse_cold_miss": 988, "hint_transient_cold_miss": 416} |
| family_protect | 7,894 | 100.00% | 1,289 | {"bypass": 314, "high": 4114, "low": 2600, "normal": 866} | {"durable": 4114, "none": 2914, "transient": 866} | {"hint_bypass_cold_miss": 109, "hint_low_reuse_cold_miss": 966, "hint_transient_cold_miss": 397} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_bypass": 317, "hint_durable_warmup": 3459, "hint_low_reuse": 2671} | {"cold_rag_burst": 317, "cold_rag_unique": 2381, "decode_heavy": 290, "durable_hot_family": 2167, "sticky_session_followup": 1292} |
| family_protect | {"hint_bypass": 314, "hint_durable_warmup": 3686, "hint_low_reuse": 2601} | {"cold_rag_burst": 314, "cold_rag_unique": 2322, "decode_heavy": 279, "durable_hot_family": 2274, "sticky_session_followup": 1412} |

## Request Class Metrics

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 314 | 82.17 | 24.938 | 32.083 | 0 |
| shared_aware | 317 | 82.95 | 24.468 | 30.983 | 0 |
| family_protect | 314 | 82.17 | 24.905 | 32.380 | 0 |

### cold_rag_unique

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 2,333 | 480.04 | 24.587 | 32.074 | 0 |
| shared_aware | 2,378 | 489.29 | 24.186 | 31.411 | 0 |
| family_protect | 2,321 | 477.58 | 24.733 | 32.350 | 0 |

### decode_heavy

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 281 | 26.39 | 108.056 | 144.257 | 0 |
| shared_aware | 290 | 27.24 | 105.309 | 140.707 | 0 |
| family_protect | 279 | 26.20 | 108.175 | 145.801 | 0 |

### durable_hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 2,655 | 414.70 | 23.974 | 31.538 | 0 |
| shared_aware | 2,698 | 421.41 | 23.551 | 30.838 | 0 |
| family_protect | 2,645 | 413.15 | 24.119 | 32.024 | 0 |

### sticky_session_followup

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,477 | 343.72 | 24.738 | 32.089 | 0 |
| shared_aware | 1,503 | 349.78 | 24.304 | 31.229 | 0 |
| family_protect | 1,469 | 341.84 | 24.853 | 32.402 | 0 |

### transient_template_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 868 | 77.97 | 23.508 | 30.870 | 0 |
| shared_aware | 880 | 79.04 | 22.977 | 30.144 | 0 |
| family_protect | 866 | 77.79 | 23.620 | 31.043 | 0 |


## Segment Metrics

### high_main

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 6,358 | 0.5577 | 556.18 | +0.00% | 28.750 | 31.569 |
| shared_aware | 6,472 | 0.5677 | 643.53 | +15.71% | 28.226 | 30.734 |
| family_protect | 6,333 | 0.5555 | 521.34 | -6.26% | 28.845 | 31.526 |

### low_guard

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 575 | 0.4792 | 1,222.53 | +0.00% | 8.563 | 10.254 |
| shared_aware | 582 | 0.4850 | 1,234.21 | +0.96% | 8.484 | 10.551 |
| family_protect | 573 | 0.4775 | 1,211.51 | -0.90% | 8.620 | 10.308 |

### red_burst

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 675 | 0.5625 | 39.19 | +0.00% | 34.912 | 37.138 |
| shared_aware | 686 | 0.5717 | 76.45 | +95.05% | 34.453 | 37.762 |
| family_protect | 668 | 0.5567 | 27.45 | -29.95% | 35.485 | 37.136 |

### warmup

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 320 | 0.5333 | 1,359.78 | +0.00% | 15.222 | 17.129 |
| shared_aware | 326 | 0.5433 | 1,385.82 | +1.92% | 14.877 | 17.961 |
| family_protect | 320 | 0.5333 | 1,359.78 | +0.00% | 15.144 | 17.752 |

## Notes

- Best throughput policy: `shared_aware` (675.80 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +1.73%; rebuilt delta vs LRU: -71.88%.
- `family_protect` total tok/s delta vs LRU: -0.44%; rebuilt delta vs LRU: -68.72%.
