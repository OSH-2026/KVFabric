# Remote qwen3_5_27b Benchmark Summary

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-17_212352_qwen3_5_27b_qwen3_5_27b_realistic_10h_pressure_long`

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Tok/s vs LRU | Avg latency s | P95 latency s | Source |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 13,021 | 0 | 1.0841 | 1,448.32 | +0.00% | 11.060 | 11.859 | final |
| shared_aware | 14,285 | 0 | 1.1893 | 1,589.19 | +9.73% | 10.081 | 11.642 | final |
| family_protect | 14,333 | 0 | 1.1933 | 1,594.54 | +10.10% | 10.049 | 11.599 | final |

## Lifecycle

| Policy | Prefix hit | Prefix hit tokens | Evicted | Rebuilt | Regret proxy | Rebuilt vs LRU |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 2.71% | 460,992 | 49,781 | 8,935 | 17.9486% | +0.00% |
| shared_aware | 12.97% | 2,417,072 | 44,708 | 60 | 0.1342% | -99.33% |
| family_protect | 12.98% | 2,425,696 | 44,859 | 68 | 0.1516% | -99.24% |

## Request Class Metrics

### ambiguous_short_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 3,872 | 407.01 | 11.065 | 11.804 | 0 |
| shared_aware | 4,252 | 446.94 | 10.224 | 11.663 | 0 |
| family_protect | 4,266 | 448.44 | 10.190 | 11.608 | 0 |

### cold_rag

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 6,210 | 763.61 | 11.195 | 11.938 | 0 |
| shared_aware | 6,830 | 839.82 | 10.340 | 11.800 | 0 |
| family_protect | 6,851 | 842.45 | 10.305 | 11.735 | 0 |

### cold_rag_burst

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 79 | 11.24 | 11.232 | 12.014 | 0 |
| shared_aware | 82 | 11.67 | 10.293 | 11.628 | 0 |
| family_protect | 82 | 11.67 | 10.308 | 11.546 | 0 |

### hot_family

| Policy | Completed | Total tok/s | Avg latency s | P95 latency s | Errors |
| :-- | --: | --: | --: | --: | --: |
| lru | 2,860 | 266.45 | 10.755 | 11.656 | 0 |
| shared_aware | 3,121 | 290.76 | 9.314 | 10.841 | 0 |
| family_protect | 3,134 | 291.98 | 9.292 | 10.850 | 0 |

## Notes

- Best throughput policy: `family_protect` (1,594.54 total tok/s).
- `shared_aware` total tok/s delta vs LRU: +9.73%; rebuilt delta vs LRU: -99.33%.
- `family_protect` total tok/s delta vs LRU: +10.10%; rebuilt delta vs LRU: -99.24%.
