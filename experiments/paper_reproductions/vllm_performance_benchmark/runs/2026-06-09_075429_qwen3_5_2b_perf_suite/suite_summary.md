# Performance Suite Summary

Run group: `2026-06-09_075429_qwen3_5_2b_perf_suite`
Baseline: **prefix_caching_on** (Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate.)

## Variant Comparison

| Variant | Req/s | Total tok/s | Out tok/s | KV Peak% | vs Baseline (req) | vs Baseline (tok) |
|:--------|:-----:|:----------:|:---------:|:--------:|:-----------------:|:-----------------:|
| prefix_caching_on | 4.92 | 2638.17 | 522.60 | 73.7% | +0.0% | +0.0% |
| vanilla_vllm | 4.84 | 2665.17 | 522.19 | 73.7% | -1.6% | +1.0% |

## Per-Variant Details

### prefix_caching_on
_Official vLLM with prefix caching enabled. Compare with vanilla_vllm to measure prefix cache overhead and hit rate._

- Prefix caching: **ON**
- Successful: 8/8 points

| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 5.93 | 1137.75 | 379.25 | 14.2 | 0.0 |
| 256 | 64 | 8.73 | 2793.62 | 558.72 | 3.5 | 0.0 |
| 256 | 128 | 5.36 | 2056.38 | 685.46 | 56.1 | 0.0 |
| 512 | 64 | 7.31 | 4209.86 | 467.76 | 69.3 | 0.0 |
| 512 | 128 | 4.60 | 2943.01 | 588.60 | 70.2 | 0.0 |
| 512 | 256 | 2.19 | 1683.94 | 561.31 | 70.2 | 0.0 |
| 1024 | 128 | 3.09 | 3559.86 | 395.54 | 70.2 | 0.0 |
| 1024 | 256 | 2.13 | 2720.96 | 544.19 | 73.7 | 0.0 |

### vanilla_vllm
_Official vLLM baseline, no KV compression, no prefix caching._

- Prefix caching: **OFF**
- Successful: 8/8 points

| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 5.76 | 1106.77 | 368.92 | 14.2 | 0.0 |
| 256 | 64 | 7.49 | 2398.04 | 479.61 | 3.5 | 0.0 |
| 256 | 128 | 5.39 | 2068.67 | 689.56 | 56.1 | 0.0 |
| 512 | 64 | 7.64 | 4401.47 | 489.05 | 70.2 | 0.0 |
| 512 | 128 | 4.72 | 3023.49 | 604.70 | 56.1 | 0.0 |
| 512 | 256 | 2.15 | 1654.45 | 551.48 | 70.2 | 0.0 |
| 1024 | 128 | 3.32 | 3819.22 | 424.36 | 70.2 | 0.0 |
| 1024 | 256 | 2.23 | 2849.25 | 569.85 | 73.7 | 0.0 |
