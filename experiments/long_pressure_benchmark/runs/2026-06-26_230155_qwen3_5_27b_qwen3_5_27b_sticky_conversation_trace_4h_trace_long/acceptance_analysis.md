# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_230155_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 2,597 | 0 | n/a | n/a | 1,202.12 | +0.00% | 0.00 pp |
| shared_aware | final | 2,597 | 0 | n/a | n/a | 1,202.23 | +0.01% | 0.00 pp |
| family_protect | final | 2,597 | 0 | n/a | n/a | 1,195.05 | -0.59% | 0.00 pp |

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

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes | Defer skips | Promote hit tokens | Promote avg hit tokens |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0.00% | 8,609 | +0.00% | 0 | 0 | 0 | 0 | 0.0 |
| shared_aware | 56,448 | 1.03% | 1,616 | -81.23% | 4,364 | 2,142 | 104 | 29,008 | 13.5 |
| family_protect | 29,792 | 0.54% | 1,628 | -81.09% | 4,344 | 2,160 | 106 | 18,816 | 8.7 |
