# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-18_174300_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | 696 | 0 | 1.1459 | 1,532.51 | n/a | 10.470 | 11.717 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 6.25% | 79,184 | 2,236 | 68 | 3.0411% | n/a |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 520 | 520 | 50.00% | 70.01% | 263 | 61.75% |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 220 | 457.34 | 10.567 | 11.780 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 333 | 809.74 | 10.584 | 11.720 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 2 | 5.63 | 10.394 | 10.665 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 141 | 259.79 | 10.052 | 11.189 | 0 |

## Notes

- Run is still in progress or some policy summaries are not yet available.
