# Performance Suite Summary

Run group: `2026-05-01_151612_qwen3_5_2b_perf_suite`
Baseline: **vanilla_vllm** (Official vLLM baseline, no KV compression, no prefix caching.)

## Variant Comparison

| Variant | Req/s | Total tok/s | Out tok/s | KV Peak% | vs Baseline (req) | vs Baseline (tok) |
|:--------|:-----:|:----------:|:---------:|:--------:|:-----------------:|:-----------------:|
| vanilla_vllm | 6.42 | 3114.02 | 655.23 | 100.0% | +0.0% | +0.0% |

## Per-Variant Details

### vanilla_vllm
_Official vLLM baseline, no KV compression, no prefix caching._

- Prefix caching: **OFF**
- Successful: 8/8 points

| Input | Output | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |
|:-----:|:------:|:-----:|:----------:|:---------:|:---------:|:-----------:|
| 128 | 64 | 12.48 | 2396.45 | 798.82 | N/A | N/A |
| 256 | 64 | 10.89 | 3485.01 | 697.00 | N/A | N/A |
| 256 | 128 | 6.85 | 2631.33 | 877.11 | 57.6 | 0.0 |
| 512 | 64 | 7.85 | 4523.96 | 502.66 | N/A | N/A |
| 512 | 128 | 4.77 | 3051.05 | 610.21 | 97.6 | 0.0 |
| 512 | 256 | 3.23 | 2483.53 | 827.84 | 100.0 | 0.0 |
| 1024 | 128 | 3.32 | 3824.31 | 424.92 | 93.6 | 0.0 |
| 1024 | 256 | 1.97 | 2516.49 | 503.30 | 44.0 | 0.0 |

