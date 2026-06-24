# Remote qwen3_5_27b KVFabric Overlay Summary

Date: 2026-06-09  
Host: robowalker, 2 x RTX 3090 24GB  
Model profile: qwen3_5_27b  
Model ID: Qwen/Qwen3.5-27B-FP8  
Environment: `/home/zhoujiarun/KVFabric/.venv_kvfabric_0221`  
vLLM: 0.22.1  
PyTorch: 2.11.0+cu129  
Overlay: KVFabric 0.22.1 overlay applied to the independent overlay venv.

## Smoke

Runtime log root:

```text
/home/zhoujiarun/KVFabric/vllm_baseline/runtime_kvfabric_0221/remote_27b_smoke/2026-06-09_083643_qwen3_5_27b_overlay_smoke
```

Result: status 0. Offline smoke, serving startup, OpenAI client verify, and
`/metrics` read all passed. The 27B-FP8 model loaded with tensor parallel 2;
vLLM reported about 14.28 GiB model memory per GPU during load.

## Initial Policy Validation

All runs used policies `lru shared_aware family_protect`.

```text
/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_084100_qwen3_5_27b_prefix_reuse_smoke_kvfabric_ab
/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_084435_qwen3_5_27b_admission_control_probe_kvfabric_ab
/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_084859_qwen3_5_27b_template_family_revisit_cycles_kvfabric_ab
/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_090153_qwen3_5_27b_cache_pressure_hot_revisit_kvfabric_ab
```

Key observations:

- `prefix_reuse_smoke`: lifecycle events and prefix lookup probe worked.
- `admission_control_probe`: 14 prefix lookups, 24,353 query tokens, 2,352
  prefix-hit tokens, 54 sealed blocks, no evictions.
- `template_family_revisit_cycles`: 328 prefix lookups, 195,405 query tokens,
  no sealed blocks on this 27B hybrid page geometry.
- `cache_pressure_hot_revisit`: 250 prefix lookups, 189,185 query tokens, but
  prompts were too short for Qwen3.5's aligned full-page behavior, so it did
  not exercise eviction policy ranking.

## Strong Pressure Fix And Rerun

Added config:

```text
experiments/prebenchmark_validation/configs/cache_pressure_hot_revisit_27b_pressure.json
```

Tokenizer check on the remote 27B tokenizer:

```text
requests=152
min_prompt_tokens=1851
max_prompt_tokens=1864
over_2048=0
```

Final fixed run:

```text
/home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-09_093708_qwen3_5_27b_cache_pressure_hot_revisit_27b_pressure_kvfabric_ab
```

| Policy | Requests | Sealed | Evicted | Ranking Events | Prefix-Hit Tokens |
|:--|--:|--:|--:|--:|--:|
| lru | 152 | 725 | 578 | 0 | 10,976 |
| shared_aware | 152 | 725 | 463 | 947 | 10,976 |
| family_protect | 152 | 725 | 578 | 518 | 10,976 |

The `shared_aware` rerun reduced evictions by 115 blocks versus LRU on the same
input. Ranking metadata was emitted after fixing the 0.22.1 overlay path:
`shared_aware` saw 231,308 hashed candidates and 4,435 protected candidates,
with 0 protected selected for eviction.

## Code Fix

The 0.22.1 pressure run exposed that the prior overlay only invoked ranking when
the first LRU victims were already protected or above a retain threshold. In
normal cached-block pressure this caused `shared_aware` and `family_protect` to
fall back to LRU while still recording `block_evicted`.

Fixed files:

```text
vllm_workspace/overlay/vllm/v1/core/block_pool.py
vllm_workspace/overlay/vllm/v1/core/kvfabric_lifecycle.py
experiments/prebenchmark_validation/examples/summarize_kvfabric_lifecycle.py
vllm_workspace/patches/vllm_overlay.patch
```

The fix makes non-LRU policies enter the selector whenever allocation would
evict cached blocks, adds `policy` to `block_evicted`, and includes eviction
events when summarizing `eviction_policies`.
