# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_032418_qwen3_5_27b_qwen3_5_27b_saturation_throughput_4h_long`

## Throughput And Latency

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | Total tok/s | Goodput vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 2,630 | 0 | n/a | 0.5464 | 584.32 | 1,420.71 | +0.00% | 27.441 | 32.247 | final |
| shared_aware | 2,670 | 0 | n/a | 0.5556 | 683.39 | 1,444.86 | +16.96% | 26.999 | 32.234 | final |
| family_protect | 2,653 | 0 | n/a | 0.5513 | 613.95 | 1,434.01 | +5.07% | 27.212 | 32.391 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 1.75% | 116,816 | 14,323 | 3,868 | 27.0055% | +0.00% |
| shared_aware | 2.65% | 215,600 | 4,587 | 1,309 | 28.5372% | -66.16% |
| family_protect | 1.85% | 152,096 | 4,781 | 1,529 | 31.9808% | -60.47% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Scheduler promotes | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0.0 | 0.00% |
| shared_aware | 2,073 | 4,709 | 81.54% | 89.28% | 589 | 644 | 87,808 | 136.3 | 82.74% |
| family_protect | 2,068 | 4,761 | 81.54% | 87.11% | 641 | 687 | 73,696 | 107.3 | 81.04% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 2,630 | 100.00% | 582 | {"bypass": 108, "high": 1353, "low": 896, "normal": 273} | {"durable": 1353, "none": 1004, "transient": 273} | {} |
| shared_aware | 2,670 | 100.00% | 590 | {"bypass": 108, "high": 1377, "low": 907, "normal": 278} | {"durable": 1377, "none": 1015, "transient": 278} | {"hint_bypass_cold_miss": 43, "hint_low_reuse_cold_miss": 383, "hint_transient_cold_miss": 163} |
| family_protect | 2,653 | 100.00% | 585 | {"bypass": 108, "high": 1367, "low": 903, "normal": 275} | {"durable": 1367, "none": 1011, "transient": 275} | {"hint_bypass_cold_miss": 47, "hint_low_reuse_cold_miss": 428, "hint_transient_cold_miss": 166} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_bypass": 108, "hint_durable_warmup": 1054, "hint_low_reuse": 911} | {"cold_rag_burst": 108, "cold_rag_unique": 811, "decode_heavy": 100, "durable_hot_family": 663, "sticky_session_followup": 391} |
| family_protect | {"hint_bypass": 108, "hint_durable_warmup": 1054, "hint_low_reuse": 906} | {"cold_rag_burst": 108, "cold_rag_unique": 806, "decode_heavy": 100, "durable_hot_family": 625, "sticky_session_followup": 429} |

## Request Class Metrics

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 108 | 84.62 | 24.553 | 31.518 | 0 |
| shared_aware | 108 | 84.76 | 24.251 | 31.811 | 0 |
| family_protect | 108 | 84.64 | 24.315 | 32.723 | 0 |

### cold_rag_unique

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 796 | 490.44 | 24.571 | 30.973 | 0 |
| shared_aware | 807 | 497.98 | 24.220 | 30.752 | 0 |
| family_protect | 803 | 494.85 | 24.344 | 30.936 | 0 |

### decode_heavy

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 100 | 28.12 | 110.122 | 142.166 | 0 |
| shared_aware | 100 | 28.17 | 109.826 | 136.423 | 0 |
| family_protect | 100 | 28.13 | 109.829 | 135.669 | 0 |

### durable_hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 865 | 404.57 | 23.776 | 30.973 | 0 |
| shared_aware | 878 | 411.29 | 23.402 | 30.304 | 0 |
| family_protect | 872 | 407.92 | 23.615 | 30.639 | 0 |

### sticky_session_followup

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 488 | 339.52 | 24.824 | 31.365 | 0 |
| shared_aware | 499 | 347.78 | 24.357 | 30.724 | 0 |
| family_protect | 495 | 344.49 | 24.654 | 31.218 | 0 |

### transient_template_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 273 | 73.43 | 22.956 | 29.560 | 0 |
| shared_aware | 278 | 74.89 | 22.444 | 28.869 | 0 |
| family_protect | 275 | 73.98 | 22.685 | 29.137 | 0 |


## Segment Metrics

### high_main

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 2,111 | 0.5555 | 531.91 | +0.00% | 29.017 | 31.010 |
| shared_aware | 2,148 | 0.5653 | 649.77 | +22.16% | 28.478 | 30.793 |
| family_protect | 2,132 | 0.5611 | 563.15 | +5.87% | 28.703 | 30.480 |

### low_guard

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 195 | 0.4875 | 1,203.62 | +0.00% | 8.549 | 9.941 |
| shared_aware | 196 | 0.4900 | 1,235.34 | +2.64% | 8.459 | 9.944 |
| family_protect | 197 | 0.4925 | 1,242.75 | +3.25% | 8.403 | 9.968 |

### red_burst

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 219 | 0.5475 | 80.13 | +0.00% | 34.720 | 35.543 |
| shared_aware | 221 | 0.5525 | 108.31 | +35.16% | 34.484 | 34.216 |
| family_protect | 219 | 0.5475 | 99.36 | +23.99% | 35.193 | 63.605 |

### warmup

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 105 | 0.5250 | 1,388.82 | +0.00% | 15.662 | 17.091 |
| shared_aware | 105 | 0.5250 | 1,388.82 | +0.00% | 15.610 | 18.023 |
| family_protect | 105 | 0.5250 | 1,388.82 | +0.00% | 15.573 | 18.208 |

## Notes

- Best throughput policy: `shared_aware` (683.39 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +1.70%; rebuilt delta vs LRU: -66.16%.
- `family_protect` total tok/s delta vs LRU: +0.94%; rebuilt delta vs LRU: -60.47%.
