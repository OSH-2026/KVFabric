# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_155220_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 2,597 | 0 | n/a | n/a | 1,072.69 | +0.00% | 0.00 pp |
| shared_aware | final | 2,528 | 69 | n/a | n/a | 1,087.30 | +1.36% | 1.84 pp |
| family_protect | final | 2,524 | 73 | n/a | n/a | 1,091.97 | +1.80% | 1.76 pp |

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
| lru | 5,488 | 0.10% | 8,594 | +0.00% | 0 | 0 | 0 | 0.0 |
| shared_aware | 156,016 | 2.55% | 1,483 | -82.74% | 4,087 | 2,428 | 136,416 | 56.2 |
| family_protect | 112,896 | 1.88% | 1,424 | -83.43% | 4,075 | 2,430 | 105,056 | 43.2 |
