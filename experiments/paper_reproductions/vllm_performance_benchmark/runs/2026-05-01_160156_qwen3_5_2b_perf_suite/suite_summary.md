# Performance Suite Summary

Run group: `2026-05-01_160156_qwen3_5_2b_perf_suite`
Baseline: **prefix_caching_on** (Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate.)

## Variant Comparison

| Variant | Req/s | Total tok/s | Out tok/s | KV Peak% | vs Baseline (req) | vs Baseline (tok) |
|:--------|:-----:|:----------:|:---------:|:--------:|:-----------------:|:-----------------:|
| prefix_caching_on | 6.07 | 2799.36 | 602.39 | 95.2% | +0.0% | +0.0% |
| vanilla_vllm | 6.45 | 3134.27 | 658.08 | 100.0% | +6.2% | +12.0% |

## Per-Variant Details

### prefix_caching_on
_Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate._

- Prefix caching: **ON**
- Successful: 8/8 points

| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 13.03 | 2502.32 | 834.11 | N/A | N/A |
| 256 | 64 | 11.00 | 3521.39 | 704.28 | N/A | N/A |
| 256 | 128 | 6.93 | 2662.05 | 887.35 | 57.6 | 0.0 |
| 512 | 64 | 6.42 | 3699.86 | 411.10 | 88.8 | 0.0 |
| 512 | 128 | 4.23 | 2707.46 | 541.49 | 92.0 | 0.0 |
| 512 | 256 | 2.49 | 1912.81 | 637.60 | 88.8 | 0.0 |
| 1024 | 128 | 2.68 | 3089.18 | 343.24 | 95.2 | 0.0 |
| 1024 | 256 | 1.80 | 2299.79 | 459.96 | 60.0 | 0.0 |

### vanilla_vllm
_Official vLLM baseline, no KV compression, no prefix caching._

- Prefix caching: **OFF**
- Successful: 8/8 points

| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 12.60 | 2419.04 | 806.35 | N/A | N/A |
| 256 | 64 | 10.86 | 3475.84 | 695.17 | N/A | N/A |
| 256 | 128 | 6.73 | 2585.99 | 862.00 | 57.6 | 0.0 |
| 512 | 64 | 7.92 | 4561.86 | 506.87 | N/A | N/A |
| 512 | 128 | 4.87 | 3119.04 | 623.81 | 97.6 | 0.0 |
| 512 | 256 | 3.25 | 2494.29 | 831.43 | 100.0 | 0.0 |
| 1024 | 128 | 3.37 | 3876.66 | 430.74 | 92.0 | 0.0 |
| 1024 | 256 | 1.99 | 2541.44 | 508.29 | 44.0 | 0.0 |

