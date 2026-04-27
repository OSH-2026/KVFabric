# 当前实验层

本目录用于承接“已经跑通 vLLM baseline”之后、“正式 benchmark 和论文复现”之前的当前阶段测试。

这里的目标不是修改历史日志或历史报告，而是沉淀一组可以反复执行的小到中等规模实验入口，用来确认脚本、模型、prefix caching、日志和结果落盘是否都可靠。

## 快速运行

从仓库根目录开始：

```bash
cd KVFabric

bash experiments/scripts/run_offline_batch.sh qwen3_5_2b

bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/scripts/run_online_batch.sh qwen3_5_2b
bash experiments/scripts/run_prefix_reuse_smoke.sh qwen3_5_2b
bash experiments/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

当前统一使用 `qwen3_5_2b` 进行验证和测试。

## 中等体量测试

如果暂时还不进入 `/home/qy-dream/OSH_Project/work` 中的标准 benchmark，可以先跑：

```bash
cd KVFabric

bash vllm_baseline/scripts/serve_local.sh qwen3_5_2b
bash experiments/scripts/run_medium_prefix_reuse.sh qwen3_5_2b
bash experiments/scripts/summarize_vllm_log.sh qwen3_5_2b
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
bash experiments/scripts/run_soak_prefix_reuse.sh qwen3_5_2b
bash experiments/scripts/summarize_vllm_log.sh qwen3_5_2b
bash vllm_baseline/scripts/stop_server.sh qwen3_5_2b
```

`soak_prefix_reuse_20min` 会发送 2400 个共享前缀请求，适合观察 prefix hit rate 是否稳定、服务日志是否异常增长。它仍不是正式 benchmark，只是当前阶段的稳定性和日志通路检查。

## 输出文件

每次运行会写入一个独立目录：

```text
experiments/runs/<timestamp>_<preset>_<experiment>/
├─ env.json
├─ config.json
├─ raw_outputs.jsonl
├─ metrics.json
└─ summary.md
```

`experiments/runs/` 下的真实运行结果默认不提交，只保留 `.gitkeep`。如果后续需要提交某次代表性结果，建议先整理成单独的阶段性分析文档，而不是直接提交大量原始输出。

## 日志摘要

服务端日志仍由 `vllm_baseline/scripts/serve_local.sh` 写入 `vllm_baseline/runtime/`。可以用下面的命令提取关键字段：

```bash
bash experiments/scripts/summarize_vllm_log.sh qwen3_5_2b
```

当前会提取：

- `enable_prefix_caching_last`
- `prefix_cache_hit_rate_last`
- `avg_prompt_throughput_last`
- `avg_generation_throughput_last`
- `gpu_kv_cache_usage_last`
- `gpu_kv_cache_size_tokens_last`
