# KVFabric Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/run_roots/enterprise_normal_medium`

## Throughput And Latency

## Trace

- Profile: `enterprise_mixed`
- Trace SHA256: `1aca4731d4ac8a652b4a07197dddff5139fad622dcb4111542939735736cbcd3`
- Requests: 4,149
- Duration seconds: 4,500.0
- Target request rate: 0.7500
- Actual request rate: 0.9220
- Hint regime: `partial_hints`
- Session request ratio: 56.81%
- Burst request ratio: 3.49%
- Unique tenants: 10
- Unique clients: 64
- Unique families: 917

## Controller Parameters

| Policy | Profile | Admission | Eviction | Scheduler | SLO protect | Hint trust | Low reuse frac | Transient frac | Bypass frac | Durable frac |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | off | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| kvfabric_admission | admission_dominant | 0.50 | 0.60 | 0.80 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | E2E goodput tok/s | Goodput vs LRU | E2E goodput vs LRU | P50 latency s | P95 latency s | P99 latency s | E2E P50 latency s | E2E P95 latency s | E2E P99 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 4,071 | 0 | 0.8635 | 0.8635 | 1,383.78 | 520.11 | +0.00% | +0.00% | 39.391 | 139.672 | 203.789 | 136.024 | 316.015 | 384.190 | final |
| kvfabric_admission | 4,071 | 0 | 0.9089 | 0.9098 | 1,624.16 | 1,600.36 | +17.37% | +207.69% | 31.065 | 107.189 | 164.061 | 33.791 | 112.722 | 171.763 | final |

## Lifecycle

| Policy | Prefix hit | Eligible hit | Warm-family hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 3.98% | 4.05% | 10.30% | 295,152 | 30,377 | 6,602 | 21.7335% | +0.00% |
| kvfabric_admission | 5.03% | 5.11% | 13.01% | 372,768 | 22,321 | 6,455 | 28.9190% | -2.23% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Latency promotes | Promotion skips | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| kvfabric_admission | 1,463 | 5,355 | 92.14% | 47.89% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons | Promotion skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 4,149 | 100.00% | 770 | {"bypass": 16, "high": 3261, "low": 619, "normal": 253} | {"durable": 3261, "none": 635, "unknown": 253} | {} | {} | {} |
| kvfabric_admission | 4,149 | 100.00% | 770 | {"bypass": 16, "high": 3261, "low": 619, "normal": 253} | {"durable": 3261, "none": 635, "unknown": 253} | {} | {} | {} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| kvfabric_admission | {"hint_bypass": 27, "hint_low_reuse": 979, "hint_unknown": 457} | {"decode_heavy_report": 354, "extraction_classification": 103, "rag_qa_cold_docs": 1006} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,215 | 468.29 | 191.95 | 44.246 | 107.500 | 294.715 | 0 |
| kvfabric_admission | 1,215 | 548.29 | 543.18 | 34.664 | 85.246 | 87.532 | 0 |

### decode_heavy_report

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 145 | 1.42 | 0.86 | 183.291 | 331.514 | 452.374 | 0 |
| kvfabric_admission | 145 | 4.60 | 4.60 | 143.964 | 268.127 | 268.129 | 0 |

### extraction_classification

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 108 | 26.88 | 10.52 | 22.612 | 56.811 | 271.240 | 0 |
| kvfabric_admission | 108 | 28.29 | 28.29 | 17.364 | 41.524 | 47.386 | 0 |

### multi_turn_support

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,142 | 347.97 | 125.44 | 44.211 | 108.959 | 293.861 | 0 |
| kvfabric_admission | 1,142 | 403.06 | 396.61 | 35.155 | 86.591 | 90.584 | 0 |

### rag_qa_cold_docs

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 635 | 257.26 | 105.11 | 67.371 | 163.281 | 327.274 | 0 |
| kvfabric_admission | 635 | 319.87 | 312.27 | 51.539 | 123.750 | 125.197 | 0 |

### rag_qa_hot_docs

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 383 | 147.63 | 51.88 | 66.396 | 161.103 | 348.291 | 0 |
| kvfabric_admission | 383 | 176.80 | 173.65 | 52.715 | 128.752 | 135.253 | 0 |

### tenant_workflow_hot

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 521 | 136.50 | 52.70 | 35.968 | 85.443 | 282.346 | 0 |
| kvfabric_admission | 521 | 144.32 | 143.30 | 28.840 | 70.822 | 75.445 | 0 |

## Notes

- Best throughput policy: `kvfabric_admission` (1,624.16 goodput tok/s).
- Best latency policy by E2E P95: `kvfabric_admission` (112.722s; reduction vs LRU: +64.33%).
- `kvfabric_admission` goodput delta vs LRU: +17.37%; E2E P95 latency reduction vs LRU: +64.33%; rebuilt delta vs LRU: -2.23%.
