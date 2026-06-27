# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_230155_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

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
| lru | 2,597 | 0 | 0.5207 | 0.5221 | n/a | 1,202.12 | +0.00% | 65.423 | 115.472 | final |
| shared_aware | 2,597 | 0 | 0.5207 | 0.5221 | n/a | 1,202.23 | +0.01% | 62.852 | 126.529 | final |
| family_protect | 2,597 | 0 | 0.5176 | 0.5190 | n/a | 1,195.05 | -0.59% | 63.876 | 126.057 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0.00% | 0 | 15,885 | 8,609 | 54.1958% | +0.00% |
| shared_aware | 1.03% | 56,448 | 3,034 | 1,616 | 53.2630% | -81.23% |
| family_protect | 0.54% | 29,792 | 3,196 | 1,628 | 50.9387% | -81.09% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| shared_aware | 3,002 | 4,364 | 60.04% | 96.19% | 24 | 104 | 2,142 | 29,008 | 13.5 | 90.21% |
| family_protect | 2,986 | 4,344 | 60.11% | 95.94% | 20 | 106 | 2,160 | 18,816 | 8.7 | 91.10% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| lru | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {} | {} |
| shared_aware | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {"hint_decode_heavy_noise_cold_miss": 18, "hint_low_reuse_cold_miss": 6} | {"defer_age_cap": 25, "low_reuse_defer_age_cap": 76, "low_reuse_defer_count_cap": 3} |
| family_protect | 2,642 | 100.00% | 779 | {"high": 2506, "low": 97, "normal": 39} | {"durable": 2506, "none": 97, "unknown": 39} | {"hint_decode_heavy_noise_cold_miss": 16, "hint_low_reuse_cold_miss": 4} | {"defer_age_cap": 26, "low_reuse_defer_age_cap": 77, "low_reuse_defer_count_cap": 3} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_durable_warmup": 2845, "hint_low_reuse": 106, "hint_unknown": 51} | {"agent_tool_loop": 439, "cold_rag_noise": 106, "decode_heavy_noise": 51, "deep_multi_turn_chat": 1454, "long_doc_followup_qa": 952} |
| family_protect | {"hint_durable_warmup": 2829, "hint_low_reuse": 106, "hint_unknown": 51} | {"agent_tool_loop": 445, "cold_rag_noise": 106, "decode_heavy_noise": 51, "deep_multi_turn_chat": 1453, "long_doc_followup_qa": 931} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 417 | 172.63 | 59.327 | 98.828 | 0 |
| shared_aware | 417 | 172.62 | 29.562 | 66.727 | 0 |
| family_protect | 417 | 171.59 | 29.419 | 66.610 | 0 |

### cold_rag_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 97 | 53.28 | 62.847 | 104.849 | 0 |
| shared_aware | 97 | 53.28 | 561.373 | 919.723 | 0 |
| family_protect | 97 | 52.97 | 565.902 | 933.639 | 0 |

### decode_heavy_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 39 | 16.49 | 127.299 | 183.875 | 0 |
| shared_aware | 39 | 16.54 | 567.624 | 995.016 | 0 |
| family_protect | 39 | 16.45 | 616.309 | 1,021.171 | 0 |

### deep_multi_turn_chat

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,384 | 556.28 | 59.093 | 100.023 | 0 |
| shared_aware | 1,384 | 556.30 | 32.870 | 72.646 | 0 |
| family_protect | 1,384 | 553.07 | 33.077 | 74.156 | 0 |

### long_doc_followup_qa

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 705 | 398.47 | 75.701 | 133.234 | 0 |
| shared_aware | 705 | 398.51 | 42.204 | 92.658 | 0 |
| family_protect | 705 | 396.16 | 42.496 | 94.525 | 0 |

## Notes

- Best throughput policy: `shared_aware` (1,202.23 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +0.01%; rebuilt delta vs LRU: -81.23%.
- `family_protect` total tok/s delta vs LRU: -0.59%; rebuilt delta vs LRU: -81.09%.
