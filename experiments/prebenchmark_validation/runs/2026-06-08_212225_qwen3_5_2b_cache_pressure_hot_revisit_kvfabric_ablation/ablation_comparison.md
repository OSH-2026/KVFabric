# KVFabric Ablation Comparison

- Run: `/home/qy-dream/OSH_Project/KVFabric/experiments/prebenchmark_validation/runs/2026-06-08_212225_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ablation`

| Variant | Evicted | Shared-anchor | Selected protected | Rebuilt | Prefix hit rate | Hit tokens | Req/s | TTFT | E2E |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lru | 759 | 0.000000 | 0 | 0 | 0.025811 | 4896 | 4.5453 | 0.100386 | 0.217554 |
| shared_aware | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.4927 | 0.102634 | 0.220117 |
| shared_no_reuse | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.5070 | 0.102173 | 0.219420 |
| shared_no_prefix | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.4958 | 0.103057 | 0.219878 |
| shared_no_recompute | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.4951 | 0.103362 | 0.219890 |
| family_protect | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.4957 | 0.103070 | 0.219879 |
| family_no_reuse | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.3052 | 0.111898 | 0.229766 |
| family_no_prefix | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.2742 | 0.112654 | 0.231340 |
| family_no_recompute | 628 | 0.000000 | 628 | 0 | 0.025811 | 4896 | 4.3382 | 0.110714 | 0.228042 |

Interpretation: use lifecycle metrics to judge whether a factor changes eviction quality; request-level metrics are useful only when the run is stable enough to compare.
