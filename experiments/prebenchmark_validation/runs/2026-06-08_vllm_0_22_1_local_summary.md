# vLLM 0.22.1 Local Laptop 4070 Summary

- Date: 2026-06-08
- Environment: `/home/qy-dream/OSH_Project/KVFabric/.venv`
- vLLM: 0.22.1
- PyTorch: 2.11.0+cu129
- CUDA available: true
- Model profile: `qwen3_5_2b` (`Qwen/Qwen3.5-2B`)
- Low-KV profile: `qwen3_5_2b_lowkv`
- Notes: top-level run directories are the current vLLM 0.22.1 records. The original `2026-04-27_*` dated paths are retained at top level, with their structured contents updated to the current 0.22.1 results. Original pre-update contents are kept under `archive_vllm_0_19_0/` and `../../../vllm_baseline/runtime/archive_vllm_0_19_0/`.

## Baseline And Prefix Results

| Run | Requests | Req/s | Completion tok/s |
|---|---:|---:|---:|
| `2026-06-08_203549_qwen3_5_2b_prefix_reuse_smoke` | 3 | 5.9621 | 15.8988 |
| `2026-06-08_203553_qwen3_5_2b_ordinary_unique_cold` | 180 | 4.3054 | 30.1376 |
| `2026-06-08_203637_qwen3_5_2b_template_family_revisit` | 200 | 4.4477 | 35.5815 |
| `2026-06-08_203725_qwen3_5_2b_template_family_revisit_cycles` | 328 | 4.6832 | 37.4653 |
| `2026-06-08_204153_qwen3_5_2b_online_batch` | 3 | 1.6796 | 34.1524 |
| `2026-06-08_204157_qwen3_5_2b_medium_prefix_reuse` | 72 | 2.1029 | 50.4697 |

Offline batch:

- `2026-06-08_203938_qwen3_5_2b_offline_batch`: 4 requests, 23.7213 output tok/s.

Cache pressure:

| Run | Requests | Req/s | Completion tok/s |
|---|---:|---:|---:|
| `2026-06-08_204235_qwen3_5_2b_cache_pressure_hot_cold` | 176 | 4.1329 | 33.0635 |
| `2026-06-08_204320_qwen3_5_2b_cache_pressure_hot_revisit` | 250 | 3.9597 | 31.6774 |
| `2026-06-08_204427_qwen3_5_2b_cache_pressure_multi_hot` | 252 | 4.8206 | 38.5647 |
| `2026-06-08_204522_qwen3_5_2b_cache_pressure_phased_hot_revisit` | 172 | 3.7087 | 29.6699 |
| `2026-06-08_204611_qwen3_5_2b_cache_pressure_ambiguous_hot_revisit` | 180 | 3.6328 | 29.0622 |

## KVFabric Overlay Results

- Overlay applied directly to `.venv` after baseline runs.
- Offline lifecycle smoke created JSONL events:
  - `vllm_baseline/runtime/kvfabric_offline_smoke_lru_2026-06-08.jsonl`
  - `vllm_baseline/runtime/kvfabric_offline_smoke_lowkv_lru_2026-06-08.jsonl`
- Online probe exposed KVFabric metrics including `kv_block_total`, `kv_block_free`, `kv_block_allocations`, prefix request metrics, and metadata update timing.

Policy A/B:

| Run | Policy | Requests | Req/s | Evicted | Ranking events |
|---|---|---:|---:|---:|---:|
| `2026-06-08_205312_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ab` | lru | 250 | 4.1408 | 759 | 0 |
| `2026-06-08_205312_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ab` | shared_aware | 250 | 3.8747 | 759 | 0 |
| `2026-06-08_205312_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ab` | family_protect | 250 | 3.9508 | 759 | 0 |
| `2026-06-08_205913_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ab` | shared_aware | 250 | 3.8561 | 628 | 1544 |
| `2026-06-08_205913_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ab` | family_protect | 250 | 4.1127 | 628 | 1544 |

Admission probe:

- `2026-06-08_212102_qwen3_5_2b_admission_control_probe_manual`
- 14 requests, 2.2507 req/s, 18.0054 completion tok/s.
- `cache_admission_limited_events`: 952
- `cache_admission_saved_blocks`: 1632
- `cache_admission_saved_ratio`: 0.631578947368421

Ablation smoke:

- `2026-06-08_212225_qwen3_5_2b_cache_pressure_hot_revisit_kvfabric_ablation`
- All 9 variants completed and produced `ablation_comparison.md`.
- Main comparison: lru evicted 759 blocks; shared/family variants evicted 628 blocks and emitted 1544 ranking events.

Low-KV profile:

- `qwen3_5_2b_lowkv` offline smoke passed with GPU KV cache size reported as 28,800 tokens.
- `2026-06-08_213751_qwen3_5_2b_lowkv_cache_pressure_hot_revisit_kvfabric_ab`
- lru/shared_aware/family_protect all completed 250 requests.
- Each policy saw 852 evicted blocks under default thresholds.
