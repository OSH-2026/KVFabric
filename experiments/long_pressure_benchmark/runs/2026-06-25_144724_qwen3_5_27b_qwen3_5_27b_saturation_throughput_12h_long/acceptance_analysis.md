# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-25_144724_qwen3_5_27b_qwen3_5_27b_saturation_throughput_12h_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 7,928 | 0 | 601.57 | +0.00% | 1,424.99 | +0.00% | 0.00 pp |
| shared_aware | final | 8,066 | 0 | 675.80 | +12.34% | 1,449.70 | +1.73% | 0.05 pp |
| family_protect | final | 7,894 | 0 | 572.13 | -4.89% | 1,418.73 | -0.44% | 0.03 pp |

## Segment: low_guard

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 575 | 0 | 0.4792 | 1,222.53 | +0.00% | 1,243.96 | 10.254 |  |
| shared_aware | 582 | 0 | 0.4850 | 1,234.21 | +0.96% | 1,255.65 | 10.551 | pass |
| family_protect | 573 | 0 | 0.4775 | 1,211.51 | -0.90% | 1,239.02 | 10.308 | pass |

## Segment: high_main

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 6,358 | 0 | 0.5577 | 556.18 | +0.00% | 1,444.50 | 31.569 |  |
| shared_aware | 6,472 | 0 | 0.5677 | 643.53 | +15.71% | 1,470.70 | 30.734 |  |
| family_protect | 6,333 | 0 | 0.5555 | 521.34 | -6.26% | 1,439.22 | 31.526 |  |

## Segment: red_burst

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 675 | 0 | 0.5625 | 39.19 | +0.00% | 1,456.22 | 37.138 |  |
| shared_aware | 686 | 0 | 0.5717 | 76.45 | +95.05% | 1,479.95 | 37.762 |  |
| family_protect | 668 | 0 | 0.5567 | 27.45 | -29.95% | 1,435.79 | 37.136 |  |

## KV Cache Evidence

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes |
| :-- | --: | --: | --: | --: | --: | --: |
| lru | 357,504 | 1.79% | 12,680 | +0.00% | 0 | 0 |
| shared_aware | 702,464 | 2.94% | 3,566 | -71.88% | 14,501 | 1,746 |
| family_protect | 224,224 | 0.96% | 3,966 | -68.72% | 14,758 | 1,651 |

## Takeaways

- Best high_main goodput policy: `shared_aware` (643.53 tok/s, +15.71% vs LRU).
- Treat total tok/s and goodput tok/s separately. Closed-loop total throughput shows raw capacity; goodput adds the SLO filter.
- If max class drift is above 3 percentage points, include a fixed-work check before making a strong throughput claim.
