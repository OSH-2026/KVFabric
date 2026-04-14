# vLLM Baseline Bring-Up Plan

## 为什么先做 vLLM 基线

KVFabric 的长期目标是做一个比现有默认 vLLM 路径更强、也更可移植的 KV Cache scheduler / runtime。但在进入自研实现前，必须先把官方 vLLM 的真实行为弄清楚，否则后续设计很容易建立在错误假设上。

本阶段需要回答的问题包括：

- vLLM 当前的 block 管理路径是什么
- prefix cache 和 scheduler 是如何配合的
- 哪些地方已经做得很好，不应重复发明
- 哪些地方确实存在未来值得重写或独立实现的空间

## 环境约束

根据 **2026-04-14** 查阅的当前官方 vLLM 安装文档与 quickstart 文档：

- GPU 安装要求的操作系统是 `Linux`
- 官方文档明确说明 `vLLM does not support Windows natively`
- 在 Windows 上运行 vLLM，官方建议路径是 `WSL` 或其他非官方维护分支

对当前这个 Windows 工作站来说，比较合理的本地基线路径是：

1. `WSL2 + Ubuntu`，优先
2. 或者使用一台原生 Linux 机器 / 远程服务器

## 推荐的本地验证顺序

### Step 1: 准备 Linux 环境

- Windows 用户优先准备 `WSL2`
- 确认 GPU 驱动、CUDA 或 ROCm 环境可被 Linux 侧识别
- 确认 Python 版本满足当前官方要求

### Step 2: 创建干净环境并安装 vLLM

官方 quickstart 推荐使用 `uv` 创建环境。最小安装路径为：

```bash
uv venv --python 3.12 --seed
source .venv/bin/activate
uv pip install vllm --torch-backend=auto
```

如果选择 `pip`，官方 GPU 安装文档也给出了直接安装方式：

```bash
pip install vllm --extra-index-url https://download.pytorch.org/whl/cu129
```

### Step 3: 跑通最小服务

先用官方 quickstart 中的最小命令跑通 OpenAI-compatible server：

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct
```

然后在本机验证：

```bash
curl http://localhost:8000/v1/models
```

### Step 4: 跑通最小离线推理

除了服务模式，还需要验证 offline inference，确认：

- 模型可以正常加载
- decode 可以正常执行
- GPU/内存占用符合预期

### Step 5: 做第一轮基线记录

至少需要记录以下信息：

- vLLM 版本
- Python 版本
- CUDA / ROCm 版本
- GPU 型号
- 操作系统与发行版
- 模型名称
- 启动命令
- 服务是否成功
- 最小推理是否成功

## 本阶段重点测试内容

完成最小 bring-up 后，下一步应聚焦：

### 1. Prefix caching 基线

- 默认前缀复用行为
- 命中与未命中的表现差异
- 对模板化 prompt 的适配情况

### 2. Scheduler 与 block 管理

- 请求进入、排队与调度路径
- block 分配与释放路径
- 驱逐与重算相关逻辑

### 3. 可观测性

- tok/s
- latency
- memory footprint
- prefix hit behavior
- 不同负载下的表现变化

## 进入自研代码阶段前的退出条件

在真正开始写 KVFabric 自身代码前，至少应满足：

- 官方 vLLM 已经成功部署
- offline / online 两条主路径已跑通
- 与 KV Cache 相关的关键调用链已经读清
- 已经形成明确的“保留什么、重写什么、抽象什么”的结论

## 参考文档

- vLLM Installation: https://docs.vllm.ai/en/latest/getting_started/installation/
- vLLM GPU Installation: https://docs.vllm.ai/en/latest/getting_started/installation/gpu/
- vLLM Quickstart: https://docs.vllm.ai/en/stable/getting_started/quickstart/
