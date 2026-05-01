# qwen3_5_2b_performance_suite

Variant: **vanilla_vllm**
Description: Official vLLM baseline, no KV compression, no prefix caching.
Model: /home/llyun/KVcasha/.cache/models/Qwen3.5-2B
GPU: NVIDIA GeForce RTX 4060 Laptop GPU

## Scan Results

| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 100 | 12.48 | 2396.45 | 798.82 | N/A | N/A |
| 256 | 64 | 100 | 10.89 | 3485.01 | 697.00 | N/A | N/A |
| 256 | 128 | 80 | 6.85 | 2631.33 | 877.11 | 57.6 | 0.0 |
| 512 | 64 | 80 | 7.85 | 4523.96 | 502.66 | N/A | N/A |
| 512 | 128 | 80 | 4.77 | 3051.05 | 610.21 | 97.6 | 0.0 |
| 512 | 256 | 50 | 3.23 | 2483.53 | 827.84 | 100.0 | 0.0 |
| 1024 | 128 | 50 | 3.32 | 3824.31 | 424.92 | 93.6 | 0.0 |
| 1024 | 256 | 30 | 1.97 | 2516.49 | 503.30 | 44.0 | 0.0 |

## Aggregate Summary

- Successful points: 8/8
- Avg request throughput: 6.42 req/s
- Avg total token throughput: 3114.02 tok/s
- Avg output token throughput: 655.23 tok/s
- Peak KV cache usage: 100.0%
- KV cache capacity: 16864 tokens (0.79 GiB)
- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)
