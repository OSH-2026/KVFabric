# Remote qwen3_5_27b Long Policy Benchmark Summary

Date: 2026-06-17  
Host: robowalker, 2 x RTX 3090 24GB  
Model profile: qwen3_5_27b  
Model ID: Qwen/Qwen3.5-27B-FP8  
Environment: `/home/zhoujiarun/KVFabric/.venv_kvfabric_0221`  
vLLM: 0.22.1  
Overlay: KVFabric 0.22.1 overlay applied to the independent overlay venv.

Raw run directories:

```text
Remote: /home/zhoujiarun/KVFabric/experiments/prebenchmark_validation/runs/2026-06-17_153658_qwen3_5_27b_qwen3_5_27b_mixed_long_pressure_long
Local:  experiments/prebenchmark_validation/runs/2026-06-17_153658_qwen3_5_27b_qwen3_5_27b_mixed_long_pressure_long
Job log: vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_formal_long.log
```

The raw run is about 234 MiB, mostly lifecycle JSONL files. It is copied back
locally but remains under the ignored `runs/` tree; this summary is the tracked
record.

## Command Shape

Script:

```text
experiments/prebenchmark_validation/scripts/run_remote_27b_long_benchmark.sh
```

Config:

```text
experiments/prebenchmark_validation/configs/qwen3_5_27b_mixed_long_pressure.json
```

Runtime settings:

| Setting | Value |
|:--|:--|
| Policies | `lru shared_aware family_protect` |
| Duration per policy | 3600 seconds |
| Warmup per policy | 120 seconds |
| Concurrency | 8 |
| `max_num_seqs` | 8 |
| `max_num_batched_tokens` | 8192 |
| Tensor parallel | 2 |
| `max_model_len` | 2048 |
| KV metrics sample | 0.05 |
| Raw output sample rate | 0.005 |

The server launched with `--max-num-seqs 8` after adding `VLLM_SERVE_*`
overrides to `vllm_baseline/scripts/serve_local.sh`.

## Throughput And Latency

| Policy | Requests | Errors | Req/s | Total tok/s | Prompt tok/s | Avg latency s | P95 latency s |
|:--|--:|--:|--:|--:|--:|--:|--:|
| lru | 4,387 | 0 | 1.2176 | 1,530.65 | 1,491.69 | 6.5659 | 8.0784 |
| shared_aware | 4,616 | 0 | 1.2807 | 1,610.30 | 1,569.32 | 6.2461 | 8.1110 |
| family_protect | 4,616 | 0 | 1.2808 | 1,610.44 | 1,569.45 | 6.2452 | 8.1218 |

Compared with LRU:

| Policy | Req/s delta | Total tok/s delta | Avg latency delta |
|:--|--:|--:|--:|
| shared_aware | +5.19% | +5.20% | -4.87% |
| family_protect | +5.20% | +5.21% | -4.89% |

## Lifecycle Metrics

| Policy | Prefix token hit rate | Prefix hit tokens | Evicted blocks | Rebuilt from eviction | Regret proxy rate | Shared-anchor eviction ratio |
|:--|--:|--:|--:|--:|--:|--:|
| lru | 12.84% | 694,624 | 14,013 | 1,229 | 8.7704% | 8.9060% |
| shared_aware | 17.17% | 971,376 | 13,304 | 4 | 0.0301% | 0.0000% |
| family_protect | 17.17% | 971,376 | 13,432 | 4 | 0.0298% | 0.0000% |

Compared with LRU:

| Policy | Rebuilt reduction | Regret-rate reduction | Prefix-hit-token delta |
|:--|--:|--:|--:|
| shared_aware | -99.67% | -99.66% | +39.84% |
| family_protect | -99.67% | -99.66% | +39.84% |

## Observations

- `shared_aware` and `family_protect` both produced a clear improvement over
  `lru` on the 27B-FP8 long pressure workload: higher throughput, lower average
  latency, higher prefix hit rate, and near-elimination of rebuilt-from-eviction.
- `shared_aware` is the cleaner default result for this workload. It matched
  `family_protect` on throughput and regret reduction while touching fewer
  ranked candidates.
- `family_protect` emitted a much higher protected-candidate ratio
  (98.54% versus 22.93% for `shared_aware`) but did not improve final outcome
  on this benchmark.
- No request errors occurred in any policy. GPU utilization stayed at 100% while
  loaded; observed temperatures were high but stable, roughly 86-89 C during the
  long run.

## Caveats

- `max_family_branch_count` remained 0 in these summaries, so the current
  benchmark still primarily validates shared-aware retention/regret behavior,
  not a fully effective explicit branch-lineage tree.
- The raw lifecycle JSONL files are intentionally not committed because the run
  directory is ignored and the copied raw data is about 234 MiB.
