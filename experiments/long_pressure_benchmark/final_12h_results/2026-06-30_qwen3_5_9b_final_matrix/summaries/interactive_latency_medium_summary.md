# KVFabric Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/run_roots/interactive_latency_medium`

## Throughput And Latency

## Trace

- Profile: `daily_dedicated_reuse`
- Trace SHA256: `e65dab704c82640248a51679a0d51055b525d967cee79730c14ce550821591a2`
- Requests: 5,006
- Duration seconds: 5,400.0
- Target request rate: 0.9000
- Actual request rate: 0.9270
- Hint regime: `partial_hints`
- Session request ratio: 68.76%
- Burst request ratio: 5.17%
- Unique tenants: 3
- Unique clients: 10
- Unique families: 137

## Controller Parameters

| Policy | Profile | Admission | Eviction | Scheduler | SLO protect | Hint trust | Low reuse frac | Transient frac | Bypass frac | Durable frac |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | off | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.05 | 0.00 | 1.00 |
| kvfabric_latency | latency_protected | 0.50 | 0.60 | 0.80 | 0.90 | 1.00 | 0.00 | 0.05 | 0.00 | 1.00 |

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | E2E goodput tok/s | Goodput vs LRU | E2E goodput vs LRU | P50 latency s | P95 latency s | P99 latency s | E2E P50 latency s | E2E P95 latency s | E2E P99 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 4,162 | 11 | 0.6006 | 0.5434 | 106.38 | 106.38 | +0.00% | +0.00% | 132.337 | 223.615 | 285.662 | 153.822 | 273.888 | 305.940 | final |
| kvfabric_latency | 4,162 | 11 | 0.6006 | 0.5836 | 423.34 | 305.23 | +297.96% | +186.94% | 69.757 | 203.591 | 287.140 | 80.727 | 221.542 | 311.271 | final |

## Error Types

| Policy | Errors |
| :-- | --: |
| lru | {"HTTPStatusError": 11} |
| kvfabric_latency | {"HTTPStatusError": 11} |

## Lifecycle

| Policy | Prefix hit | Eligible hit | Warm-family hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 8.56% | 9.15% | 15.31% | 795,960 | 30,915 | 10,845 | 35.0801% | +0.00% |
| kvfabric_latency | 10.54% | 11.26% | 18.85% | 980,100 | 29,902 | 9,788 | 32.7314% | -9.75% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Latency promotes | Promotion skips | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| kvfabric_latency | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 3,442 | 0 | 0 | 0.0 | 0.00% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons | Promotion skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 4,995 | 100.00% | 104 | {"bypass": 22, "high": 3814, "low": 360, "normal": 799} | {"durable": 3814, "none": 382, "unknown": 799} | {} | {} | {} |
| kvfabric_latency | 4,995 | 100.00% | 104 | {"bypass": 22, "high": 3814, "low": 360, "normal": 799} | {"durable": 3814, "none": 382, "unknown": 799} | {} | {} | {} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| kvfabric_latency | {} | {} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,159 | 44.77 | 44.77 | 115.059 | 192.849 | 246.209 | 0 |
| kvfabric_latency | 1,159 | 149.27 | 108.29 | 59.984 | 124.891 | 136.808 | 0 |

### background_cold_lookup

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 382 | 20.52 | 20.52 | 100.134 | 178.398 | 217.490 | 0 |
| kvfabric_latency | 382 | 17.92 | 17.92 | 121.871 | 193.071 | 245.073 | 0 |

### decode_heavy_background

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 450 | 2.94 | 2.94 | 204.445 | 295.385 | 330.395 | 0 |
| kvfabric_latency | 450 | 2.94 | 2.94 | 231.630 | 314.576 | 355.577 | 0 |

### deep_multi_turn_chat

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 641 | 27.14 | 27.14 | 107.911 | 193.448 | 242.968 | 0 |
| kvfabric_latency | 641 | 88.38 | 70.02 | 54.137 | 111.034 | 133.376 | 0 |

### long_doc_research_followup

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 439 | 26.07 | 26.07 | 126.462 | 202.574 | 245.434 | 11 |
| kvfabric_latency | 439 | 52.70 | 44.12 | 76.030 | 150.514 | 150.830 | 11 |

### project_code_followup

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,192 | 89.80 | 89.80 | 117.323 | 222.724 | 266.814 | 0 |
| kvfabric_latency | 1,192 | 182.26 | 149.05 | 74.463 | 163.919 | 178.573 | 0 |

### short_chat_qa

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 349 | 6.10 | 6.10 | 80.599 | 153.401 | 196.477 | 0 |
| kvfabric_latency | 349 | 7.94 | 5.61 | 58.185 | 86.080 | 91.316 | 0 |

### tenant_workflow_hot

| Policy | Completed | Goodput tok/s | E2E goodput tok/s | Avg latency s | P95 latency s | E2E P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 382 | 31.30 | 31.30 | 65.675 | 150.507 | 218.928 | 0 |
| kvfabric_latency | 382 | 49.52 | 44.44 | 35.581 | 71.887 | 89.736 | 0 |

## Notes

- Best throughput policy: `kvfabric_latency` (423.34 goodput tok/s).
- `kvfabric_latency` goodput delta vs LRU: +297.96%; E2E P95 latency reduction vs LRU: -61.96%; rebuilt delta vs LRU: -9.75%.
- `kvfabric_latency` latency-promoted class E2E P95 reductions: 6/6 classes >= 30%; range +33.07% to +59.01%.
