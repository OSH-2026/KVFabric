# KVFabric Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/run_roots/low_reuse`

## Throughput And Latency

## Trace

- Profile: `low_reuse_low_frequency`
- Trace SHA256: `4150873b548f3c9ace769eba57aab581612617e41fcca0c641d22aeefdbfe838`
- Requests: 742
- Duration seconds: 2,700.0
- Target request rate: 0.2500
- Actual request rate: 0.2748
- Hint regime: `partial_hints`
- Session request ratio: 0.00%
- Burst request ratio: 0.94%
- Unique tenants: 12
- Unique clients: 96
- Unique families: 648

## Controller Parameters

| Policy | Profile | Admission | Eviction | Scheduler | SLO protect | Hint trust | Low reuse frac | Transient frac | Bypass frac | Durable frac |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | off | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| kvfabric_admission | admission_dominant | 0.50 | 0.60 | 0.80 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | E2E goodput tok/s | Goodput vs LRU | E2E goodput vs LRU | P50 latency s | P95 latency s | P99 latency s | E2E P50 latency s | E2E P95 latency s | E2E P99 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 727 | 0 | 0.2496 | 0.2496 | 317.95 | 153.28 | +0.00% | +0.00% | 29.178 | 174.143 | 260.320 | 151.216 | 325.620 | 382.412 | final |
| kvfabric_admission | 727 | 0 | 0.2746 | 0.2751 | 448.88 | 448.88 | +41.18% | +192.86% | 3.361 | 15.796 | 21.139 | 3.362 | 15.798 | 21.141 | final |

## Lifecycle

| Policy | Prefix hit | Eligible hit | Warm-family hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0.00% | 0.00% | 0.00% | 0 | 4,348 | 0 | 0.0000% | n/a |
| kvfabric_admission | 0.00% | 0.00% | 0.00% | 0 | 777 | 0 | 0.0000% | n/a |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Latency promotes | Promotion skips | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| kvfabric_admission | 863 | 2,293 | 80.65% | 10.85% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons | Promotion skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 742 | 100.00% | 0 | {"bypass": 1, "low": 193, "normal": 548} | {"none": 194, "unknown": 548} | {} | {} | {} |
| kvfabric_admission | 742 | 100.00% | 0 | {"bypass": 1, "low": 193, "normal": 548} | {"none": 194, "unknown": 548} | {} | {} | {} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| kvfabric_admission | {"hint_bypass": 2, "hint_low_reuse": 311, "hint_unknown": 550} | {"decode_heavy_background": 412, "extraction_classification": 129, "rag_qa_cold_docs": 313, "single_turn_api_task": 9} |

## Request Class Metrics

### decode_heavy_background

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 179 | 49.15 | 27.48 | 129.239 | 245.269 | 379.764 | 0 |
| kvfabric_admission | 179 | 131.98 | 131.98 | 12.507 | 20.359 | 20.361 | 0 |

### extraction_classification

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 138 | 56.20 | 30.08 | 16.493 | 41.035 | 252.232 | 0 |
| kvfabric_admission | 138 | 61.82 | 61.82 | 1.815 | 3.782 | 3.786 | 0 |

### rag_qa_cold_docs

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 194 | 168.83 | 77.53 | 49.804 | 129.841 | 303.513 | 0 |
| kvfabric_admission | 194 | 204.04 | 204.04 | 5.472 | 11.181 | 11.181 | 0 |

### short_chat_qa

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 109 | 13.73 | 7.56 | 15.377 | 44.438 | 244.128 | 0 |
| kvfabric_admission | 109 | 15.10 | 15.10 | 1.588 | 3.376 | 3.378 | 0 |

### single_turn_api_task

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 122 | 31.47 | 15.39 | 25.850 | 81.210 | 271.484 | 0 |
| kvfabric_admission | 122 | 34.60 | 34.60 | 2.722 | 6.749 | 6.763 | 0 |

## Notes

- Best throughput policy: `kvfabric_admission` (448.88 goodput tok/s).
- Best latency policy by E2E P95: `kvfabric_admission` (15.798s; reduction vs LRU: +95.15%).
- `kvfabric_admission` goodput delta vs LRU: +41.18%; E2E P95 latency reduction vs LRU: +95.15%; rebuilt delta vs LRU: n/a.
