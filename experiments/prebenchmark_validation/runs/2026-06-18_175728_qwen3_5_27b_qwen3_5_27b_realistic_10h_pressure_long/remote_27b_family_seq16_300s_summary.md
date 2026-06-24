# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-18_175728_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |  |  |
| family_protect | 352 | 0 | 1.1429 | 1,523.42 | n/a | 13.995 | 15.882 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 5.63% | 32,928 | 1,124 | 59 | 5.2491% | n/a |

## Admission And Scheduler

| Policy | Admission limited | Saved blocks | Saved ratio | Admission risk avg | Scheduler defers | Defer risk avg |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |  |
| shared_aware | pending |  |  |  |  |  |
| family_protect | 0 | 0 | 0.00% | 0.00% | 91 | 61.06% |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 108 | 442.76 | 14.033 | 15.852 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 167 | 800.83 | 14.128 | 15.883 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | pending |  |  |  |  |
| shared_aware | pending |  |  |  |  |
| family_protect | 77 | 279.83 | 13.653 | 15.879 | 0 |

## Notes

- Run is still in progress or some policy summaries are not yet available.
