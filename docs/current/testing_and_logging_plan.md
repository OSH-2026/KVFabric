# 当前可做测试与日志方案

本文档只描述当前阶段还能做什么，不替代仓库同级目录 `../work/` 里的正式 benchmark 任务。

## 当前已可运行的测试

- `offline_batch`：离线批量请求，验证模型加载、批处理和结果落盘。
- `online_batch`：在线 OpenAI-compatible API 顺序请求，记录平均延迟、p50、p95 和 token 数。
- `prefix_reuse_smoke`：小规模共享前缀 smoke，确认服务路径可用。
- `medium_prefix_reuse`：中等规模共享前缀测试，当前默认 72 个请求，适合观察 prefix hit rate。
- `soak_prefix_reuse_20min`：可选长时间稳定性测试，默认 2400 个请求，用于把热缓存状态下的运行时间拉长到接近 20 分钟量级。

## 本机已观察结果

在 `qwen3_5_2b`、`max_model_len=1024`、`ENABLE_PREFIX_CACHING=1` 下：

- 共享前缀不足一个 full block 时，日志中的 prefix cache hit rate 仍为 `0.0%`。
- 将共享系统前缀调到约 716 input tokens 后，`medium_prefix_reuse` 可以观察到 prefix cache hit rate 上升到约 `74.9%`。
- 当前热缓存状态下，72 个请求的中等测试约 `35.77s` 完成，因此它更适合做功能性验证，不适合当作长时间 benchmark。

## 还可以补充的测试

- 冷启动对比：清理或更换 torch compile cache 后记录启动、warmup 和首轮请求时间。
- Prefix on/off 对比：同一组请求分别用 `ENABLE_PREFIX_CACHING=1` 和 `ENABLE_PREFIX_CACHING=0` 跑，比较 TTFT、prompt throughput 和 prefix hit rate。
- 长上下文边界：在 `max_model_len=1024` 内改变共享前缀长度，覆盖低于 full block、刚超过 full block、接近上限三类情况。
- 并发轻测：把 `concurrency` 从 1 提到 2 或 4，观察排队、延迟 p95 和 prefix hit 是否稳定。
- Soak 稳定性：使用 `run_soak_prefix_reuse.sh` 长时间发送共享前缀请求，观察 prefix hit rate 是否保持、KV cache usage 是否异常增长。

## 推荐添加的 vLLM 日志点

后续进入源码原型时，可以优先在 vLLM Python 控制面加轻量日志或 side table，不改 CUDA kernel。

- `vllm/v1/core/kv_cache_manager.py`
  记录 `get_computed_blocks()` 的 query tokens、hit tokens、是否 skip prefix cache。

- `vllm/v1/core/block_pool.py`
  记录 `cache_full_blocks()` 的 block hash、block id、prefix depth；记录 `_maybe_evict_cached_block()` 的 evicted block id、hash、idle time。

- `vllm/v1/core/single_type_kv_cache_manager.py`
  记录 `find_longest_cache_hit()` 的 longest hit blocks，以及第一次 miss 的位置。

- `vllm/v1/core/sched/scheduler.py`
  记录每个新请求的 `num_cached_tokens`、`num_computed_tokens`、本 step 需要实际计算的 token 数。

- `vllm/v1/metrics/stats.py`
  扩展已有 prefix cache stats，后续可增加 block 级 hit、eviction regret、rebuild count。

## 日志输出建议

第一阶段不要直接在热路径里打印大量普通日志。更稳妥的做法是：

- 默认关闭详细日志；
- 通过环境变量或配置开关启用；
- 先写 JSONL 事件，例如 `kv_lifecycle_events.jsonl`；
- 事件按 request/block 粒度记录，不记录大 tensor；
- 中等测试和 soak 测试结束后用脚本汇总。
