# vLLM Baseline

这个文档负责说明 KVFabric 当前使用的项目级基线：为什么先做 `vLLM`、运行它需要什么前提、仓库里已经准备了哪些入口，以及什么时候可以离开 baseline 阶段进入后续设计。

如果你想直接执行脚本，请先看：

- [`vllm_baseline/README.md`](../../vllm_baseline/README.md)
- [`logs/2026-04-14-vllm-bringup.md`](../../logs/2026-04-14-vllm-bringup.md)

## 当前快照

- 默认验证模型：`Qwen/Qwen2.5-0.5B-Instruct`
- 已验证能力：offline inference + online serving
- 可选预设：`Qwen/Qwen3-8B`
- 运行方式：相对仓库根目录的脚本化工作流

`Qwen/Qwen3-8B` 保留为后续更大显存机器上的对照选项，不作为当前这台 `8 GiB` GPU 的默认 bring-up 目标。

## 为什么先做 vLLM

KVFabric 的长期方向是独立的 KV Cache scheduler / runtime，但第一步不是自己写一套运行时，而是先把参考系统跑通、看清、测明白。对于当前仓库，这个参考系统就是官方 `vLLM`。

这一阶段最关心的是：

- `vLLM` 现在如何管理 KV blocks
- `prefix cache` 和 `scheduler` 是怎样配合工作的
- 哪些能力值得保留，哪些地方值得在后续系统里重做
- 哪些约束会直接影响未来 C++ 模块边界

## 环境约束

按 `2026-04-14` 查阅的官方安装文档，`vLLM` 的 GPU 安装目标系统是 `Linux`，并且官方明确说明 `vLLM does not support Windows natively`。

对这台 Windows 工作站，推荐路径是：

1. `WSL2 + Ubuntu`
2. 或者原生 Linux 机器 / 远程服务器

开始之前，至少先确认：

- Linux 侧能正常识别 GPU
- Python 版本满足官方要求
- 代理或网络环境足以访问官方安装源和 Hugging Face

## 快速执行

仓库已经把常用 bring-up 流程收敛到了 `vllm_baseline/`：

```bash
cd KVFabric
cd vllm_baseline

bash scripts/setup_venv.sh
bash scripts/download_model.sh qwen2_5_0_5b_instruct
bash scripts/run_offline_smoke.sh qwen2_5_0_5b_instruct
bash scripts/serve_local.sh qwen2_5_0_5b_instruct
bash scripts/verify_server.sh qwen2_5_0_5b_instruct
bash scripts/stop_server.sh qwen2_5_0_5b_instruct
```

官方 quickstart 常见的是直接执行类似下面的命令：

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct
```

仓库里之所以默认切到 `qwen2_5_0_5b_instruct`，只是为了给当前这台机器保留一条更轻、更稳、更容易复现的最小链路。

## 预期现象

服务启动后，下面这些现象都正常：

- `/docs`：FastAPI / Swagger UI 页面
- `/health`：浏览器里可能像空白页，只用于健康检查
- `/v1/models`：返回 JSON；如果出现 `qwen2.5-0.5b-local`，说明模型已经加载成功

常用的验证方式有三种：

- 在 `/docs` 里用 `Try it out`
- 用 `curl` 调 `POST /v1/chat/completions`
- 用 `vllm_baseline/examples/openai_client_smoke.py`

## 建议记录

第一轮基线记录建议至少包含：

- `vLLM` 版本
- Python 版本
- CUDA / ROCm 版本
- GPU 型号
- 操作系统与发行版
- 模型名称
- 启动命令
- 服务是否成功
- 最小推理是否成功

仓库内可直接引用的记录入口：

- [`logs/2026-04-14-vllm-bringup.md`](../../logs/2026-04-14-vllm-bringup.md)
- [`vllm_baseline/runtime/`](../../vllm_baseline/runtime/) 下的临时运行日志

## 下一步关注点

完成最小 bring-up 之后，下一步建议集中在：

- prefix caching 的命中行为和稳定复现方式
- scheduler 与 block 分配、释放、驱逐路径
- latency、tok/s、memory footprint 和 prefix reuse 相关观测

## 退出条件

进入自研实现之前，至少需要满足：

- 官方 `vLLM` 已成功部署
- offline / online 两条主路径已跑通
- 与 KV Cache 相关的关键调用链已基本读清
- 已形成明确的“保留什么、重写什么、抽象什么”的结论

## 参考资料

- vLLM Installation: https://docs.vllm.ai/en/latest/getting_started/installation/
- vLLM GPU Installation: https://docs.vllm.ai/en/latest/getting_started/installation/gpu/
- vLLM Quickstart: https://docs.vllm.ai/en/stable/getting_started/quickstart/
