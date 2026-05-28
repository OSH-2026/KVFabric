# qwen3_5_2b_performance_suite

Variant: **prefix_caching_on**
Description: Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate.
Model: /home/llyun/KVcasha/.cache/models/Qwen3.5-2B
GPU: NVIDIA GeForce RTX 4060 Laptop GPU

## Scan Results

| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 100 | 13.03 | 2502.32 | 834.11 | N/A | N/A |
| 256 | 64 | 100 | 11.00 | 3521.39 | 704.28 | N/A | N/A |
| 256 | 128 | 80 | 6.93 | 2662.05 | 887.35 | 57.6 | 0.0 |
| 512 | 64 | 80 | 6.42 | 3699.86 | 411.10 | 88.8 | 0.0 |
| 512 | 128 | 80 | 4.23 | 2707.46 | 541.49 | 92.0 | 0.0 |
| 512 | 256 | 50 | 2.49 | 1912.81 | 637.60 | 88.8 | 0.0 |
| 1024 | 128 | 50 | 2.68 | 3089.18 | 343.24 | 95.2 | 0.0 |
| 1024 | 256 | 30 | 1.80 | 2299.79 | 459.96 | 60.0 | 0.0 |

## Aggregate Summary

- Successful points: 8/8
- Avg request throughput: 6.07 req/s
- Avg total token throughput: 2799.36 tok/s
- Avg output token throughput: 602.39 tok/s
- Peak KV cache usage: 95.2%
- KV cache capacity: 16864 tokens (0.79 GiB)
- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)
