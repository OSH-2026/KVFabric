# KVFabric Acceptance Run Analysis

Run root: `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-26_032418_qwen3_5_27b_qwen3_5_27b_saturation_throughput_4h_long`

## Overall

| Policy | Source | Completed | Errors | Goodput tok/s | Goodput vs LRU | Total tok/s | Total vs LRU | Max class drift |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | final | 2,630 | 0 | 584.32 | +0.00% | 1,420.71 | +0.00% | 0.00 pp |
| shared_aware | final | 2,670 | 0 | 683.39 | +16.96% | 1,444.86 | +1.70% | 0.13 pp |
| family_protect | final | 2,653 | 0 | 613.95 | +5.07% | 1,434.01 | +0.94% | 0.10 pp |

## Segment: low_guard

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 195 | 0 | 0.4875 | 1,203.62 | +0.00% | 1,244.84 | 9.941 |  |
| shared_aware | 196 | 0 | 0.4900 | 1,235.34 | +2.64% | 1,252.26 | 9.944 | pass |
| family_protect | 197 | 0 | 0.4925 | 1,242.75 | +3.25% | 1,259.67 | 9.968 | pass |

## Segment: high_main

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 2,111 | 0 | 0.5555 | 531.91 | +0.00% | 1,441.35 | 31.010 |  |
| shared_aware | 2,148 | 0 | 0.5653 | 649.77 | +22.16% | 1,467.07 | 30.793 |  |
| family_protect | 2,132 | 0 | 0.5611 | 563.15 | +5.87% | 1,455.90 | 30.480 |  |

## Segment: red_burst

| Policy | Completed | Errors | Req/s | Goodput tok/s | Goodput vs LRU | Total tok/s | P95 latency s | Verdict |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 219 | 0 | 0.5475 | 80.13 | +0.00% | 1,450.19 | 35.543 |  |
| shared_aware | 221 | 0 | 0.5525 | 108.31 | +35.16% | 1,462.35 | 34.216 |  |
| family_protect | 219 | 0 | 0.5475 | 99.36 | +23.99% | 1,453.91 | 63.605 |  |

## KV Cache Evidence

| Policy | Prefix hit tokens | Prefix hit rate | Rebuilt blocks | Rebuilt vs LRU | Admission saved blocks | Scheduler promotes | Promote hit tokens | Promote avg hit tokens |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| lru | 116,816 | 1.75% | 3,868 | +0.00% | 0 | 0 | 0 | 0.0 |
| shared_aware | 215,600 | 2.65% | 1,309 | -66.16% | 4,709 | 644 | 87,808 | 136.3 |
| family_protect | 152,096 | 1.85% | 1,529 | -60.47% | 4,761 | 687 | 73,696 | 107.3 |

## Takeaways

- Best high_main goodput policy: `shared_aware` (649.77 tok/s, +22.16% vs LRU).
- Treat total tok/s and goodput tok/s separately. Closed-loop total throughput shows raw capacity; goodput adds the SLO filter.
- If max class drift is above 3 percentage points, include a fixed-work check before making a strong throughput claim.
