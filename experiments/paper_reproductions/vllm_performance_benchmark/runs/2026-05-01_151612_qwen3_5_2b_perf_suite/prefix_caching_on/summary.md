# qwen3_5_2b_performance_suite

Variant: **prefix_caching_on**
Description: Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate.
Model: /home/qy-dream/OSH_Project/KVFabric/.cache/models/Qwen3.5-2B
GPU: NVIDIA GeForce RTX 4070 Laptop GPU

## Scan Results

| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 100 | 5.93 | 1137.75 | 379.25 | 14.2 | 0.0 |
| 256 | 64 | 100 | 8.73 | 2793.62 | 558.72 | 3.5 | 0.0 |
| 256 | 128 | 80 | 5.36 | 2056.38 | 685.46 | 56.1 | 0.0 |
| 512 | 64 | 80 | 7.31 | 4209.86 | 467.76 | 69.3 | 0.0 |
| 512 | 128 | 80 | 4.60 | 2943.01 | 588.60 | 70.2 | 0.0 |
| 512 | 256 | 50 | 2.19 | 1683.94 | 561.31 | 70.2 | 0.0 |
| 1024 | 128 | 50 | 3.09 | 3559.86 | 395.54 | 70.2 | 0.0 |
| 1024 | 256 | 30 | 2.13 | 2720.96 | 544.19 | 73.7 | 0.0 |

## Aggregate Summary

- Successful points: 8/8
- Avg request throughput: 4.92 req/s
- Avg total token throughput: 2638.17 tok/s
- Avg output token throughput: 522.60 tok/s
- Peak KV cache usage: 73.7%
- KV cache capacity: 23552 tokens (0.72 GiB)
- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)
