# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-27_143948_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 3,551 | 0 | 1,202.27 | +0.00% | 1,204.52 | +0.00% | 0.00 pp |
| shared_aware | final | 3,551 | 0 | 1,196.51 | -0.48% | 1,209.81 | +0.44% | 0.00 pp |
| family_protect | final | 3,551 | 0 | 1,190.90 | -0.95% | 1,204.51 | -0.00% | 0.00 pp |

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

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes | Defer skips | Promotion skips | Promote hit tokens | Promote avg hit tokens |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 0 | 0.00% | 11,555 | +0.00% | 0 | 0 | 0 | 0 | 0 | 0.0 |
| shared_aware | 32,928 | 0.44% | 2,209 | -80.88% | 6,040 | 191 | 177 | 226 | 32,144 | 168.3 |
| family_protect | 7,056 | 0.09% | 2,224 | -80.75% | 6,035 | 182 | 178 | 227 | 7,056 | 38.8 |
