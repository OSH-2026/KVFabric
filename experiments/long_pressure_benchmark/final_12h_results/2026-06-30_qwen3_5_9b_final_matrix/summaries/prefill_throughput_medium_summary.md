# KVFabric Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/run_roots/prefill_throughput_medium`

## Throughput And Latency

## Controller Parameters

| Policy | Profile | Admission | Eviction | Scheduler | SLO protect | Hint trust | Low reuse frac | Transient frac | Bypass frac | Durable frac |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | off | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.05 | 0.00 | 1.00 |
| kvfabric_throughput | throughput_protect | 0.50 | 0.60 | 0.80 | 0.00 | 1.00 | 0.00 | 0.05 | 0.00 | 1.00 |

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | E2E goodput tok/s | Goodput vs LRU | E2E goodput vs LRU | P50 latency s | P95 latency s | P99 latency s | E2E P50 latency s | E2E P95 latency s | E2E P99 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 11,520 | 0 | n/a | 1.5622 | 1,815.04 | n/a | +0.00% | n/a | 40.925 | 45.707 | 47.464 | n/a | n/a | n/a | final |
| kvfabric_throughput | 12,105 | 0 | n/a | 1.6391 | 3,590.21 | n/a | +97.80% | n/a | 32.649 | 35.977 | 38.372 | n/a | n/a | n/a | final |

## Lifecycle

| Policy | Prefix hit | Eligible hit | Warm-family hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 21.28% | 37.29% | 41.41% | 7,587,360 | 81,330 | 11,790 | 14.4965% | +0.00% |
| kvfabric_throughput | 30.93% | 66.06% | 71.11% | 11,491,920 | 54,030 | 1,725 | 3.1927% | -85.37% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Latency promotes | Promotion skips | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| kvfabric_throughput | 26,115 | 68,475 | 50.00% | 90.26% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons | Promotion skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 11,520 | 100.00% | 63 | {"bypass": 1200, "high": 5175, "low": 4680, "normal": 465} | {"durable": 5175, "none": 5880, "transient": 465} | {} | {} | {} |
| kvfabric_throughput | 12,105 | 100.00% | 64 | {"bypass": 1275, "high": 5400, "low": 4950, "normal": 480} | {"durable": 5400, "none": 6225, "transient": 480} | {} | {} | {} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| kvfabric_throughput | {"hint_bypass": 6375, "hint_low_reuse": 19740} | {"cold_rag_burst": 6375, "cold_rag_unique": 19740} |

## Request Class Metrics

### cold_rag_burst

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,200 | 131.20 | n/a | 40.007 | 45.275 | n/a | 0 |
| kvfabric_throughput | 1,275 | 349.39 | n/a | 37.303 | 41.704 | n/a | 0 |

### cold_rag_unique

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 4,665 | 516.97 | n/a | 38.987 | 45.908 | n/a | 0 |
| kvfabric_throughput | 4,935 | 1,216.88 | n/a | 37.322 | 42.837 | n/a | 0 |

### decode_heavy

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 15 | 0.00 | n/a | 136.154 | 136.154 | n/a | 0 |
| kvfabric_throughput | 15 | 0.00 | n/a | 148.403 | 148.403 | n/a | 0 |

### durable_hot_family

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 3,780 | 485.36 | n/a | 38.311 | 45.664 | n/a | 0 |
| kvfabric_throughput | 3,930 | 1,279.58 | n/a | 36.549 | 41.683 | n/a | 0 |

### sticky_session_followup

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,395 | 670.35 | n/a | 29.911 | 37.537 | n/a | 0 |
| kvfabric_throughput | 1,470 | 705.35 | n/a | 28.656 | 36.052 | n/a | 0 |

### transient_template_family

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 465 | 11.15 | n/a | 39.241 | 45.323 | n/a | 0 |
| kvfabric_throughput | 480 | 39.01 | n/a | 37.664 | 41.704 | n/a | 0 |


## Segment Metrics

### cold_churn_main

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 108,964 | 1.6143 | 1,246.66 | +0.00% | 40.762 | 45.016 |
| kvfabric_throughput | 113,063 | 1.6750 | 3,131.16 | +151.16% | 38.965 | 41.929 |

### durable_revisit

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 42,300 | 1.5667 | 1,928.59 | +0.00% | 37.762 | 47.316 |
| kvfabric_throughput | 47,250 | 1.7500 | 4,693.11 | +143.34% | 34.898 | 43.012 |

### working_set_warmup

| Policy | Completed | Req/s | Goodput tok/s | Goodput vs LRU | Avg latency s | P95 latency s |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 21,600 | 1.6000 | 3,897.66 | +0.00% | 28.052 | 44.169 |
| kvfabric_throughput | 21,600 | 1.6000 | 4,096.48 | +5.10% | 28.001 | 41.483 |

## Notes

- Best throughput policy: `kvfabric_throughput` (3,590.21 goodput tok/s).
- Best latency policy by P95: `kvfabric_throughput` .
- `kvfabric_throughput` goodput delta vs LRU: +97.80%; E2E P95 latency reduction vs LRU: n/a; rebuilt delta vs LRU: -85.37%.
- Selected SLO probe: 40s.
