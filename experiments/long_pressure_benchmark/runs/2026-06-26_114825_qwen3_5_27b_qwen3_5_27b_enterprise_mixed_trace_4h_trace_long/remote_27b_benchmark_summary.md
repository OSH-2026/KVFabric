# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_114825_qwen3_5_27b_qwen3_5_27b_enterprise_mixed_trace_4h_trace_long`

## Throughput And Latency

## Trace

- Profile: `enterprise_mixed`
- Trace SHA256: `cec75222d7fe1ad11b079596b77f8e15a569249d828bcb99c27165ef2f21037f`
- Requests: 1,055
- Duration seconds: 4,800.0
- Target request rate: 0.1800
- Actual request rate: 0.2198
- Hint regime: `partial_hints`

| Policy | Requests | Errors | Offered req/s | Req/s | Goodput tok/s | Total tok/s | Goodput vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 1,034 | 0 | 0.2196 | 0.2198 | n/a | 437.27 | +0.00% | 8.909 | 22.712 | final |
| shared_aware | 1,034 | 0 | 0.2196 | 0.2198 | n/a | 437.27 | +0.00% | 9.097 | 23.081 | final |
| family_protect | 1,034 | 0 | 0.2196 | 0.2198 | n/a | 437.25 | -0.00% | 8.967 | 22.794 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 13.39% | 247,744 | 5,224 | 757 | 14.4908% | +0.00% |
| shared_aware | 8.86% | 164,640 | 2,029 | 358 | 17.6442% | -52.71% |
| family_protect | 10.31% | 192,080 | 2,086 | 268 | 12.8476% | -64.60% |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Scheduler promotes | Promote hit tokens | Promote avg hit tokens | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0 | 0.00% | 0.00% | 0 | 0 | 0 | 0.0 | 0.00% |
| shared_aware | 768 | 1,297 | 69.54% | 94.58% | 4 | 5 | 0 | 0.0 | 69.90% |
| family_protect | 727 | 1,251 | 70.36% | 90.78% | 6 | 6 | 784 | 130.7 | 74.22% |

## Hint-Aware Behavior

| Policy | Hint events | Coverage | Hint families | Priorities | Expected reuse | Defer reasons |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 1,055 | 100.00% | 207 | {"high": 831, "low": 155, "normal": 69} | {"durable": 831, "none": 155, "unknown": 69} | {} |
| shared_aware | 1,055 | 100.00% | 207 | {"high": 831, "low": 155, "normal": 69} | {"durable": 831, "none": 155, "unknown": 69} | {"hint_decode_heavy_report_cold_miss": 1, "hint_low_reuse_cold_miss": 3} |
| family_protect | 1,055 | 100.00% | 207 | {"high": 831, "low": 155, "normal": 69} | {"durable": 831, "none": 155, "unknown": 69} | {"hint_decode_heavy_report_cold_miss": 1, "hint_low_reuse_cold_miss": 5} |

## Admission Reasons

| Policy | Admission reasons | Limited hint classes |
| :-- | --: | --: |
| lru | {} | {} |
| shared_aware | {"hint_durable_warmup": 528, "hint_low_reuse": 200, "hint_unknown": 40} | {"agent_tool_loop": 291, "decode_heavy_report": 40, "multi_turn_support": 86, "rag_qa_cold_docs": 200, "rag_qa_hot_docs": 149, "tenant_workflow_hot": 2} |
| family_protect | {"hint_durable_warmup": 487, "hint_low_reuse": 200, "hint_unknown": 40} | {"agent_tool_loop": 284, "decode_heavy_report": 40, "multi_turn_support": 57, "rag_qa_cold_docs": 200, "rag_qa_hot_docs": 144, "tenant_workflow_hot": 2} |

## Request Class Metrics

### agent_tool_loop

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 270 | 117.90 | 7.792 | 17.621 | 0 |
| shared_aware | 270 | 117.90 | 8.335 | 19.000 | 0 |
| family_protect | 270 | 117.90 | 8.280 | 17.664 | 0 |

### decode_heavy_report

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 34 | 14.66 | 28.208 | 46.557 | 0 |
| shared_aware | 34 | 14.66 | 28.508 | 45.088 | 0 |
| family_protect | 34 | 14.66 | 28.199 | 45.022 | 0 |

### extraction_classification

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 35 | 8.79 | 4.529 | 9.742 | 0 |
| shared_aware | 35 | 8.79 | 4.524 | 9.735 | 0 |
| family_protect | 35 | 8.79 | 4.454 | 9.628 | 0 |

### multi_turn_support

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 317 | 111.91 | 7.700 | 17.271 | 0 |
| shared_aware | 317 | 111.92 | 7.719 | 17.658 | 0 |
| family_protect | 317 | 111.91 | 7.543 | 17.265 | 0 |

### rag_qa_cold_docs

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 155 | 90.20 | 11.866 | 28.156 | 0 |
| shared_aware | 155 | 90.20 | 11.904 | 28.396 | 0 |
| family_protect | 155 | 90.20 | 11.732 | 28.191 | 0 |

### rag_qa_hot_docs

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 106 | 57.57 | 11.023 | 23.800 | 0 |
| shared_aware | 106 | 57.57 | 11.137 | 23.929 | 0 |
| family_protect | 106 | 57.56 | 11.011 | 23.813 | 0 |

### tenant_workflow_hot

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 138 | 36.12 | 6.127 | 14.859 | 0 |
| shared_aware | 138 | 36.12 | 6.224 | 14.870 | 0 |
| family_protect | 138 | 36.12 | 6.146 | 14.584 | 0 |

## Notes

- Best throughput policy: `shared_aware` (437.27 goodput tok/s).
- `shared_aware` total tok/s delta vs LRU: +0.00%; rebuilt delta vs LRU: -52.71%.
- `family_protect` total tok/s delta vs LRU: -0.00%; rebuilt delta vs LRU: -64.60%.
