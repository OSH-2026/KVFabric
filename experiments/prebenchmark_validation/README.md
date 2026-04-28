# Prebenchmark Validation

本目录承接“已经跑通 vLLM baseline”之后、“正式 benchmark 和论文复现”之前的预基准验证工作。

它的职责不是替代正式 benchmark，也不是直接承载论文复现，而是先把当前机器、当前模型、当前脚本链路验证扎实：模型能否稳定加载、服务能否稳定启动、共享前缀能否观测到命中、日志和结果是否能标准化落盘。

这套内容现在被单独收拢到 `experiments/prebenchmark_validation/`，方便后续把正式 benchmark 放到 `experiments/benchmarks/`，把论文复现放到 `experiments/paper_reproductions/`。

## 目录结构

```text
prebenchmark_validation/
├─ README.md
├─ configs/
├─ examples/
├─ runs/
└─ scripts/
```

## 适用范围

- baseline 跑通后的快速回归
- prefix caching 功能性验证
- 小到中等规模的在线请求复现
- 进入正式 benchmark 前的参数、日志和输出通路检查

## 快速运行

从仓库根目录开始：

```bash
cd KVFabric

bash experiments/prebenchmark_validation/scripts/run_offline_batch.sh qwen3_5_2b

bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_online_batch.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_prefix_reuse_smoke.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

当前统一使用 `qwen3_5_2b` 进行验证和测试。

如果希望直接跑一遍完整的预验证流程，也可以使用：

```bash
cd KVFabric

bash experiments/prebenchmark_validation/scripts/run_validation_suite.sh qwen3_5_2b
```

如果还想顺便把中等体量共享前缀测试一起带上：

```bash
bash experiments/prebenchmark_validation/scripts/run_validation_suite.sh qwen3_5_2b --with-medium
```

## 中等体量测试

如果暂时还不进入仓库同级目录 `../work/` 中的正式 benchmark，可以先跑：

```bash
cd KVFabric

bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_medium_prefix_reuse.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

这个测试会发送一组共享系统前缀的在线请求，用来观察：

- prefix cache 是否开启；
- prefix cache hit rate 是否出现；
- 在线请求平均延迟、p50、p95；
- prompt/completion token 数；
- completion tokens/s；
- GPU KV cache usage 的日志变化。

当前 `medium_prefix_reuse` 默认使用 72 个请求。热缓存状态下可能不到 1 分钟完成。如果希望做 20 分钟左右的稳定性观察，可以改跑：

```bash
bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/run_soak_prefix_reuse.sh qwen3_5_2b
bash experiments/prebenchmark_validation/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

`soak_prefix_reuse_20min` 会发送 2400 个共享前缀请求，适合观察 prefix hit rate 是否稳定、服务日志是否异常增长。它仍不是正式 benchmark，只是当前阶段的稳定性和日志通路检查。

## 输出文件

每次运行会写入一个独立目录：

```text
experiments/prebenchmark_validation/runs/<timestamp>_<preset>_<experiment>/
├─ env.json
├─ config.json
├─ raw_outputs.jsonl
├─ metrics.json
└─ summary.md
```

`runs/` 下的真实运行结果默认不提交，只保留 `.gitkeep`。如果后续需要提交某次代表性结果，建议先整理成单独的阶段性分析文档，而不是直接提交大量原始输出。

当前脚本会根据配置文件名自动生成更清晰的 run 目录名，例如：

- `..._offline_batch`
- `..._online_batch`
- `..._medium_prefix_reuse`
- `..._prefix_reuse_smoke`
- `..._soak_prefix_reuse_20min`

## 日志摘要

服务端日志仍由 `vllm_baseline/scripts/serve_local.sh` 写入 `vllm_baseline/runtime/`。可以用下面的命令提取关键字段：

```bash
bash experiments/prebenchmark_validation/scripts/summarize_vllm_log.sh qwen3_5_2b
```

当前会提取：

- `enable_prefix_caching_last`
- `prefix_cache_hit_rate_last`
- `avg_prompt_throughput_last`
- `avg_generation_throughput_last`
- `gpu_kv_cache_usage_last`
- `gpu_kv_cache_size_tokens_last`
