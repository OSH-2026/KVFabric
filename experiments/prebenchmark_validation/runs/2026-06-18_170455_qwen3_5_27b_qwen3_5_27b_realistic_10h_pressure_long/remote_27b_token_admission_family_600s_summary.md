# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-18_170455_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | 690 | 0 | 1.1420 | 1,527.03 | n/a | 10.485 | 11.771 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 5.81% | 77,616 | 2,222 | 68 | 3.0603% | n/a |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 0 | 0 | 0.00% | 0.00% | 324 | 67.21% |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 220 | 459.73 | 10.573 | 11.861 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 329 | 804.20 | 10.725 | 11.860 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 2 | 5.66 | 10.916 | 10.981 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 139 | 257.45 | 9.771 | 11.320 | 0 |

## Notes

- Run is still in progress or some policy summaries are not yet available.
