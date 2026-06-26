# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_114825_qwen3_5_27b_qwen3_5_27b_enterprise_mixed_trace_4h_trace_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 1,034 | 0 | n/a | n/a | 437.27 | +0.00% | 0.00 pp |
| shared_aware | final | 1,034 | 0 | n/a | n/a | 437.27 | +0.00% | 0.00 pp |
| family_protect | final | 1,034 | 0 | n/a | n/a | 437.25 | -0.00% | 0.00 pp |

## Segment: low_guard

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | pending |  |  |  |  |  |  |  |

## Segment: high_main

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | pending |  |  |  |  |  |  |  |

## Segment: red_burst

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | pending |  |  |  |  |  |  |  |

## KV Cache Evidence

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes | Promote hit tokens | Promote avg hit tokens |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 247,744 | 13.39% | 757 | +0.00% | 0 | 0 | 0 | 0.0 |
| shared_aware | 164,640 | 8.86% | 358 | -52.71% | 1,297 | 5 | 0 | 0.0 |
| family_protect | 192,080 | 10.31% | 268 | -64.60% | 1,251 | 6 | 784 | 130.7 |
