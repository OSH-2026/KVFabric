# Qwen3.5-9B Final Matrix Sync And Analysis

Updated: 2026-06-30 20:15 CST

## Archive Status

- Remote tail job `qwen9b_12h_tail_enterprise_lowreuse_20260630` finished.
- Tail modules were synced into this final result root at 2026-06-30 19:52 CST.
- Four final summaries are present:
  - `summaries/prefill_throughput_medium_summary.md`
  - `summaries/interactive_latency_medium_summary.md`
  - `summaries/enterprise_normal_medium_summary.md`
  - `summaries/low_reuse_summary.md`
- The summaries were regenerated after sync so the main tables and final notes use
  the same current calculation code.

## Main Results

| Stage | KVFabric profile | Main claim | LRU | KVFabric | Delta |
| :-- | :-- | :-- | --: | --: | --: |
| `prefill_throughput_medium` | `kvfabric_throughput` | selected SLO goodput tok/s | 1815.04 | 3590.21 | +97.80% |
| `interactive_latency_medium` | `kvfabric_latency` | overall e2e P95 latency s | 273.888 | 221.542 | +19.11% reduction |
| `enterprise_normal_medium` | `kvfabric_admission` | e2e P95 latency s | 316.015 | 112.722 | +64.33% reduction |
| `enterprise_normal_medium` | `kvfabric_admission` | goodput tok/s | 1383.78 | 1624.16 | +17.37% |
| `low_reuse` | `kvfabric_admission` | e2e P95 latency s | 325.620 | 15.798 | +95.15% reduction |
| `low_reuse` | `kvfabric_admission` | goodput tok/s | 317.95 | 448.88 | +41.18% |

## Lifecycle Evidence

| Stage | Prefix hit | Warm-family hit | Evicted blocks | Rebuilt-from-eviction |
| :-- | :-- | :-- | :-- | :-- |
| `prefill_throughput_medium` | 21.28% -> 30.93% | 41.41% -> 71.11% | 81330 -> 54030 | 11790 -> 1725 (-85.37%) |
| `interactive_latency_medium` | 8.56% -> 10.54% | 15.31% -> 18.85% | 30915 -> 29902 | 10845 -> 9788 (-9.75%) |
| `enterprise_normal_medium` | 3.98% -> 5.03% | 10.30% -> 13.01% | 30377 -> 22321 | 6602 -> 6455 (-2.23%) |
| `low_reuse` | 0.00% -> 0.00% | 0.00% -> 0.00% | 4348 -> 777 | 0 -> 0 |

## Interpretation

`prefill_throughput_medium` is the cleanest throughput proof. It shows both a
large selected-SLO goodput gain and strong lifecycle causality: higher prefix hit,
higher warm-family hit, fewer evictions, and much lower rebuilt-from-eviction.
This is the stage to cite for high-pressure prefill/prefix-reuse throughput.

`interactive_latency_medium` should be reported as a foreground-priority latency
stage, not as a blanket overall 30% latency win. Overall e2e P95 improves by
19.11%, while all six protected foreground classes improve by at least 30%
in e2e P95. The guard/background classes regress:
`background_cold_lookup` by 12.68% and `decode_heavy_background` by 7.62%.

`enterprise_normal_medium` is stronger than expected for a normal mixed service
stage. It improves goodput by 17.37% and e2e P95 latency by 64.33% with zero
errors. The lifecycle hit-rate improvement is modest, and rebuilt only drops
2.23%, so this should be interpreted mainly as admission reducing cache churn,
queue backlog, and low-value cache pressure, not as a pure prefix-reuse result.

`low_reuse` passes the non-degradation guard and in this run improves substantially.
There are no prefix hits and no rebuilt events on either policy, so the result
does not prove prefix reuse. It shows that hint-aware admission can avoid wasting
cache capacity on one-shot/low-reuse requests: admission saved 2293 blocks,
evictions fell from 4348 to 777, and e2e P95 fell from 325.620s to 15.798s.

## Recommended Claims

- In the Qwen3.5-9B medium-capacity prefill throughput stage, KVFabric improves
  selected-SLO goodput by +97.80% while reducing rebuilt-from-eviction by 85.37%.
- In the foreground-priority latency stage, KVFabric reduces e2e P95 latency by
  at least 30% for all protected foreground classes, with explicit background
  guard regressions.
- In the enterprise mixed stage, KVFabric improves goodput by +17.37% and e2e
  P95 latency by +64.33%, mainly through admission and lower cache churn.
- In low-reuse/low-frequency traffic, KVFabric does not degrade; in this run it
  improves goodput and latency by avoiding low-value cache admission.

## Cautions

- Do not present `low_reuse` as a prefix-reuse win; prefix hit and rebuilt are
  both zero.
- Do not present `interactive_latency_medium` as an overall 30% latency reduction;
  the defensible 30%+ claim is class-level foreground latency protection.
- For `enterprise_normal_medium`, the performance gain is real in this run, but
  the lifecycle evidence points more to admission/backlog control than to a large
  reuse/rebuild mechanism.
