# qwen3_5_2b_performance_suite

Variant: **vanilla_vllm**
Description: Official vLLM baseline, no KV compression, no prefix caching.
Model: /home/llyun/KVcasha/.cache/models/Qwen3.5-2B
GPU: NVIDIA GeForce RTX 4060 Laptop GPU

## Scan Results

| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 100 | 12.60 | 2419.04 | 806.35 | N/A | N/A |
| 256 | 64 | 100 | 10.86 | 3475.84 | 695.17 | N/A | N/A |
| 256 | 128 | 80 | 6.73 | 2585.99 | 862.00 | 57.6 | 0.0 |
| 512 | 64 | 80 | 7.92 | 4561.86 | 506.87 | N/A | N/A |
| 512 | 128 | 80 | 4.87 | 3119.04 | 623.81 | 97.6 | 0.0 |
| 512 | 256 | 50 | 3.25 | 2494.29 | 831.43 | 100.0 | 0.0 |
| 1024 | 128 | 50 | 3.37 | 3876.66 | 430.74 | 92.0 | 0.0 |
| 1024 | 256 | 30 | 1.99 | 2541.44 | 508.29 | 44.0 | 0.0 |

## Aggregate Summary

- Successful points: 8/8
- Avg request throughput: 6.45 req/s
- Avg total token throughput: 3134.27 tok/s
- Avg output token throughput: 658.08 tok/s
- Peak KV cache usage: 100.0%
- KV cache capacity: 16864 tokens (0.79 GiB)
- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)
