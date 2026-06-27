# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-27_143948_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

## Throughput And Latency

## Trace

- Profile: `conversation_sticky`
- Trace SHA256: `9f0f14da89336197d744545acfd9bfdba4b98984dc45697cd05638865e1a25f5`
- Requests: 3,614
- Duration seconds: 4,800.0
- Target request rate: 0.6200
- Actual request rate: 0.7529
- Hint regime: `partial_hints`

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | Total tok/s | Goodput vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 3,551 | 0 | 0.5256 | 0.5241 | 1,202.27 | 1,204.52 | +0.00% | 119.486 | 171.099 | final |
| shared_aware | 3,551 | 0 | 0.5279 | 0.5264 | 1,196.51 | 1,209.81 | -0.48% | 118.492 | 170.369 | final |
| family_protect | 3,551 | 0 | 0.5256 | 0.5241 | 1,190.90 | 1,204.51 | -0.95% | 118.825 | 170.161 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 0.00% | 0 | 21,856 | 11,555 | 52.8688% | +0.00% |
| shared_aware | 0.44% | 32,928 | 4,060 | 2,209 | 54.4089% | -80.88% |
| family_protect | 0.09% | 7,056 | 4,151 | 2,224 | 53.5775% | -80.75% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer skips | Scheduler promotes | Promotion skips | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00% |
| shared_aware | 4,166 | 6,040 | 60.06% | 95.41% | 46 | 177 | 191 | 226 | 32,144 | 168.3 | 87.09% |
| family_protect | 4,174 | 6,035 | 59.88% | 94.72% | 47 | 178 | 182 | 227 | 7,056 | 38.8 | 86.26% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons | Defer skip reasons | Promotion skip reasons |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 3,614 | 100.00% | 1,108 | {"high": 3431, "low": 133, "normal": 50} | {"durable": 3431, "none": 133, "unknown": 50} | {} | {} | {} |
| shared_aware | 3,614 | 100.00% | 1,108 | {"high": 3431, "low": 133, "normal": 50} | {"durable": 3431, "none": 133, "unknown": 50} | {"hint_decode_heavy_noise_cold_miss": 46} | {"defer_age_cap": 46, "low_reuse_defer_age_cap": 131} | {"head_age_guard": 93, "low_reuse_head_age_guard": 133} |
| family_protect | 3,614 | 100.00% | 1,108 | {"high": 3431, "low": 133, "normal": 50} | {"durable": 3431, "none": 133, "unknown": 50} | {"hint_decode_heavy_noise_cold_miss": 47} | {"defer_age_cap": 47, "low_reuse_defer_age_cap": 131} | {"head_age_guard": 94, "low_reuse_head_age_guard": 133} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_durable_warmup": 3950, "hint_low_reuse": 155, "hint_unknown": 61} | {"agent_tool_loop": 598, "cold_rag_noise": 155, "decode_heavy_noise": 61, "deep_multi_turn_chat": 1968, "long_doc_followup_qa": 1384} |
| family_protect | {"hint_durable_warmup": 3958, "hint_low_reuse": 155, "hint_unknown": 61} | {"agent_tool_loop": 605, "cold_rag_noise": 155, "decode_heavy_noise": 61, "deep_multi_turn_chat": 1973, "long_doc_followup_qa": 1380} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 550 | 168.04 | 111.659 | 155.585 | 0 |
| shared_aware | 550 | 168.78 | 109.579 | 153.677 | 0 |
| family_protect | 550 | 168.05 | 110.103 | 153.775 | 0 |

### cold_rag_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 133 | 53.68 | 112.873 | 155.788 | 0 |
| shared_aware | 133 | 53.91 | 113.691 | 156.094 | 0 |
| family_protect | 133 | 53.68 | 113.473 | 156.078 | 0 |

### decode_heavy_noise

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 50 | 15.30 | 192.957 | 252.472 | 0 |
| shared_aware | 50 | 15.37 | 275.653 | 358.073 | 0 |
| family_protect | 50 | 15.30 | 276.716 | 354.281 | 0 |

### deep_multi_turn_chat

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,868 | 550.78 | 113.013 | 154.108 | 0 |
| shared_aware | 1,868 | 553.19 | 111.369 | 153.842 | 0 |
| family_protect | 1,868 | 550.77 | 111.780 | 154.153 | 0 |

### long_doc_followup_qa

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 1,013 | 418.80 | 128.337 | 189.585 | 0 |
| shared_aware | 1,013 | 420.58 | 124.744 | 187.698 | 0 |
| family_protect | 1,013 | 418.79 | 124.875 | 188.398 | 0 |

## Notes

- Best throughput policy: `lru` (1,202.27 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +0.44%; rebuilt delta vs LRU: -80.88%.
- `family_protect` total tok/s delta vs LRU: -0.00%; rebuilt delta vs LRU: -80.75%.
