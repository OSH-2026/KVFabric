# M4.5 过渡阶段计划

本文档描述当前项目阶段：它位于已经归档的 vLLM bring-up 记录之后，也位于仓库同级目录 `../work/` 中正式 benchmark 和论文方法复现之前。

历史日志、历史报告、前期调研都视为只读归档材料。当前新增的实验入口、日志摘要、源码工作区和阶段计划放在当前阶段目录中维护。

## 当前目标

- 在正式 benchmark 前补充小到中等规模的可复现实验。
- 统一使用 `qwen3_5_2b` 作为当前验证和测试模型。
- 确认 prefix caching 能否显式开启，并能在共享前缀场景中观察到命中。
- 标准化运行输出，方便后续与正式 benchmark 对接。
- 准备 vLLM Python 控制面的源码 overlay，方便后续做生命周期统计和策略修改。

## 当前目录

- `experiments/prebenchmark_validation/`：当前阶段批量测试、在线测试、prefix reuse smoke、中等体量测试和日志摘要。
- `vllm_workspace/`：vLLM v0.19.0 选定源码文件的 overlay 和 patch 工作流。
- `docs/current/`：当前阶段计划与说明。

## Prefix Caching 说明

Prefix caching 会在请求之间复用已经计算好的 KV block。当前请求如果和之前请求共享完全相同的 full-block 前缀，vLLM 可以直接复用这些 block，从而减少重复 prefill。

它主要用于观察和优化：

- 重复 system prompt；
- 模板化 prompt；
- RAG 文档公共前缀；
- 多轮对话共享历史；
- 高价值前缀 block 的保留和驱逐。

当前脚本通过 profile 中的 `ENABLE_PREFIX_CACHING=1` 显式传递 `--enable-prefix-caching`。实测 `qwen3_5_2b` 可以进入 `enable_prefix_caching=True` 初始化路径，但 vLLM 会提示其 Mamba prefix caching 仍是实验性支持。因此当前可以用它做主模型测试，同时在解释结果时记录该实验性边界。

## 当前建议顺序

1. 使用 `qwen3_5_2b` 跑 `run_offline_batch.sh`，确认离线批处理和结果落盘正常。
2. 启动 `qwen3_5_2b` 服务，跑 `run_online_batch.sh`，确认在线请求路径正常。
3. 跑 `run_prefix_reuse_smoke.sh`，确认共享前缀 smoke 能执行。
4. 跑 `run_medium_prefix_reuse.sh`，进行中等体量的共享前缀请求测试。
5. 跑 `summarize_vllm_log.sh`，从 server log 中提取 prefix hit rate、吞吐和 KV cache usage。
6. 后续若要修改 vLLM，先在 `vllm_workspace/overlay/` 中做改动，再导出 patch 或应用到完整 `vllm-v0.19.0` 工作树。

## 本机时间估算

在当前 RTX 4070 Laptop GPU 8 GiB + WSL2 环境下：

- `qwen3_5_2b` 离线 smoke：约 2 到 4 分钟，首次编译或缓存变化时更久。
- `qwen3_5_2b` 离线 batch：约 3 到 8 分钟。
- `qwen3_5_2b` 服务启动：约 3 到 8 分钟，首次 warmup 可能接近或超过 10 分钟。
- `qwen3_5_2b` 在线 smoke：服务启动后通常 1 到 3 分钟内完成。
- `qwen3_5_2b` 中等 prefix reuse 测试：热缓存状态下本机实测约 1 分钟内完成，更适合做功能性验证。
- `qwen3_5_2b` soak prefix reuse 测试：预计接近 20 分钟量级，用于稳定性和日志通路观察。
- `../work/` 中的正式 benchmark 矩阵：预计几十分钟到数小时。
