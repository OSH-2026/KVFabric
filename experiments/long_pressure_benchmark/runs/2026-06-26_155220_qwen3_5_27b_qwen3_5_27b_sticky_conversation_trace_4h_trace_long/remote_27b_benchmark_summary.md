# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_155220_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

## Throughput And Latency

## Trace

- Profile: `conversation_sticky`
- Trace SHA256: `7de5e340b7f2892f5f5c1fa83720a06a9ebbf9c033bef4d43360997569a5ac8e`
- Requests: 2,642
- Duration seconds: 4,800.0
- Target request rate: 0.4500
- Actual request rate: 0.5504
- Hint regime: `partial_hints`

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | Total tok/s | Goodput vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 2,597 | 0 | 0.4656 | 0.4659 | n/a | 1,072.69 | +0.00% | 66.660 | 99.489 | final |
| shared_aware | 2,528 | 69 | 0.4862 | 0.4739 | n/a | 1,087.30 | +1.36% | 37.706 | 90.684 | final |
| family_protect | 2,524 | 73 | 0.4889 | 0.4758 | n/a | 1,091.97 | +1.80% | 36.403 | 78.529 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0.10% | 5,488 | 15,850 | 8,594 | 54.2208% | +0.00% |
| shared_aware | 2.55% | 156,016 | 2,811 | 1,483 | 52.7570% | -82.74% |
| family_protect | 1.88% | 112,896 | 2,941 | 1,424 | 48.4189% | -83.43% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Scheduler promotes | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0.0 | 0.00% |
| shared_aware | 2,858 | 4,087 | 59.31% | 98.11% | 354 | 2,428 | 136,416 | 56.2 | 95.64% |
| family_protect | 2,848 | 4,075 | 59.33% | 97.92% | 309 | 2,430 | 105,056 | 43.2 | 95.22% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {} |
| shared_aware | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {"hint_decode_heavy_noise_cold_miss": 58, "hint_low_reuse_cold_miss": 296} |
| family_protect | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {"hint_decode_heavy_noise_cold_miss": 57, "hint_low_reuse_cold_miss": 252} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_durable_warmup": 2777, "hint_low_reuse": 54, "hint_unknown": 27} | {"agent_tool_loop": 431, "cold_rag_noise": 54, "decode_heavy_noise": 27, "deep_multi_turn_chat": 1409, "long_doc_followup_qa": 937} |
| family_protect | {"hint_durable_warmup": 2774, "hint_low_reuse": 55, "hint_unknown": 19} | {"agent_tool_loop": 443, "cold_rag_noise": 55, "decode_heavy_noise": 19, "deep_multi_turn_chat": 1418, "long_doc_followup_qa": 913} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 417 | 154.36 | 61.539 | 86.819 | 0 |
| shared_aware | 417 | 161.18 | 24.480 | 52.153 | 0 |
| family_protect | 417 | 162.04 | 23.905 | 51.994 | 0 |

### cold_rag_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 97 | 47.64 | 64.334 | 91.478 | 0 |
| shared_aware | 47 | 24.24 | 392.189 | 859.389 | 50 |
| family_protect | 49 | 25.25 | 389.597 | 879.242 | 48 |

### decode_heavy_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 39 | 14.80 | 110.035 | 146.125 | 0 |
| shared_aware | 20 | 7.88 | 231.125 | 692.962 | 19 |
| family_protect | 14 | 5.68 | 206.433 | 674.280 | 25 |

### deep_multi_turn_chat

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,384 | 497.42 | 62.251 | 88.886 | 0 |
| shared_aware | 1,384 | 519.45 | 29.708 | 88.906 | 0 |
| family_protect | 1,384 | 522.27 | 28.123 | 74.889 | 0 |

### long_doc_followup_qa

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 705 | 356.30 | 73.425 | 110.653 | 0 |
| shared_aware | 705 | 372.02 | 31.026 | 68.166 | 0 |
| family_protect | 705 | 374.09 | 31.239 | 68.361 | 0 |

## Notes

- Best throughput policy: `family_protect` (1,091.97 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +1.36%; rebuilt delta vs LRU: -82.74%.
- `family_protect` total tok/s delta vs LRU: +1.80%; rebuilt delta vs LRU: -83.43%.
