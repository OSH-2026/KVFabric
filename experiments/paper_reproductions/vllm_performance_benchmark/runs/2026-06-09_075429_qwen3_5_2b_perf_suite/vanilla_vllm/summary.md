# qwen3_5_2b_performance_suite

Variant: **vanilla_vllm**
Description: Official vLLM baseline, no KV compression, no prefix caching.
Model: /home/qy-dream/OSH_Project/KVFabric/.cache/models/Qwen3.5-2B
GPU: NVIDIA GeForce RTX 4070 Laptop GPU

## Scan Results

| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 100 | 5.76 | 1106.77 | 368.92 | 14.2 | 0.0 |
| 256 | 64 | 100 | 7.49 | 2398.04 | 479.61 | 3.5 | 0.0 |
| 256 | 128 | 80 | 5.39 | 2068.67 | 689.56 | 56.1 | 0.0 |
| 512 | 64 | 80 | 7.64 | 4401.47 | 489.05 | 70.2 | 0.0 |
| 512 | 128 | 80 | 4.72 | 3023.49 | 604.70 | 56.1 | 0.0 |
| 512 | 256 | 50 | 2.15 | 1654.45 | 551.48 | 70.2 | 0.0 |
| 1024 | 128 | 50 | 3.32 | 3819.22 | 424.36 | 70.2 | 0.0 |
| 1024 | 256 | 30 | 2.23 | 2849.25 | 569.85 | 73.7 | 0.0 |

## Aggregate Summary

- Successful points: 8/8
- Avg request throughput: 4.84 req/s
- Avg total token throughput: 2665.17 tok/s
- Avg output token throughput: 522.19 tok/s
- Peak KV cache usage: 73.7%
- KV cache capacity: 33645 tokens (0.72 GiB)
- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)
