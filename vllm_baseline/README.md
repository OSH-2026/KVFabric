# vLLM Baseline Workspace

这个目录用于在当前仓库内独立完成 `vLLM` 的环境配置、模型下载、offline smoke test、online serving smoke test，以及最基本的 OpenAI-compatible API 使用验证。

它的定位是：

- 为当前 `KVFabric` 项目提供一个可重复执行的 `vLLM` 基线工作区
- 不包含 KVFabric 自研 runtime 实现
- 默认复用仓库根目录下的 `.venv` 与 `.cache`，避免重复下载和重复安装

## 目录结构

```text
vllm_baseline/
├─ README.md
├─ configs/
│  └─ env.example
├─ examples/
│  ├─ offline_smoke.py
│  └─ openai_client_smoke.py
├─ profiles/
│  ├─ qwen2_5_0_5b_instruct.env
│  └─ qwen3_8b.env
└─ scripts/
   ├─ collect_env.sh
   ├─ common.sh
   ├─ download_model.sh
   ├─ run_offline_smoke.sh
   ├─ serve_local.sh
   ├─ setup_venv.sh
   ├─ stop_server.sh
   └─ verify_server.sh
```

## 已验证环境

以下环境已经在本机实际验证通过：

- 日期：`2026-04-14`
- OS：`Ubuntu 24.04.1 LTS` on `WSL2`
- Python：`3.12.3`
- GPU：`NVIDIA GeForce RTX 4070 Laptop GPU (8 GiB)`
- Driver：`581.83`
- PyTorch：`2.10.0+cu129`
- vLLM：`0.19.0`

## GitHub 提交边界

这个工作区现在适合提交到 GitHub，但只应提交：

- `vllm_baseline/README.md`
- `vllm_baseline/configs/`
- `vllm_baseline/profiles/`
- `vllm_baseline/scripts/`
- `vllm_baseline/examples/`
- 与之配套的 `.gitignore` 调整

不应提交：

- `.venv/`
- `.cache/`
- `vllm_baseline/.env.local`
- `vllm_baseline/runtime/` 下的日志和 PID
- `__pycache__/`、`.pyc`

也就是说，当前目录已经被整理成“可分享的脚本和文档”，而不是“绑死在某一台机器上的运行结果”。

## 两个模型预设

### 1. 默认小模型

- 预设名：`qwen2_5_0_5b_instruct`
- 官方模型：`Qwen/Qwen2.5-0.5B-Instruct`
- 用途：当前机器的最小可运行 smoke test
- 结论：已在本机跑通 offline + online

### 2. 可选大模型

- 预设名：`qwen3_8b`
- 官方模型：`Qwen/Qwen3-8B`
- 用途：后续更接近真实 serving 的可选基线
- 备注：
  - 按 `2026-04-14` 的 Hugging Face 官方 API 实测，公开可访问的是 `Qwen/Qwen3-8B`
  - 同日 `Qwen/Qwen3-8B-Instruct` 在当前环境里返回了 `401`
  - `Qwen/Qwen3-8B` 是官方公开模型，因此本目录采用它作为可选预设
  - 这个模型以 `bf16` 形式运行时通常不适合当前这张 `8 GiB` 显存的 GPU，请优先在更大显存机器上使用

## 默认路径约定

本目录下的脚本默认使用以下路径：

- Python 环境：`.venv`
- 模型缓存：`.cache/models`
- Hugging Face 缓存：`.cache/huggingface`
- vLLM 编译/运行缓存：`.cache/vllm`
- 运行日志与 PID：`vllm_baseline/runtime/`

这些值在配置层都写成“相对 `KVFabric/` 仓库根目录”的形式。  
如果你想改成单独的虚拟环境或单独的缓存目录，可以复制 `configs/env.example` 为 `.env.local` 后修改。

## 适用前提

最推荐的运行环境：

- Linux
- 或 Windows + `WSL2 + Ubuntu`
- NVIDIA GPU 场景下建议先确认 `nvidia-smi` 正常
- Python `3.12`

最小检查：

```bash
python3 --version
uname -a
nvidia-smi
```

如果是全新 Linux / WSL 环境，建议先准备这些基础工具：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl
```

如果你是从 GitHub 新 clone 下来的仓库，一个最典型的起点是：

```bash
git clone <your-repo-url> KVFabric
cd KVFabric
cd vllm_baseline
```

## 从零开始的完整教程

下面的流程假设其他同学刚刚 clone 了仓库，还没有任何本地环境。

### Step 0: 进入目录

```bash
cd KVFabric
cd vllm_baseline
```

### Step 1: 可选，配置代理或覆盖默认路径

如果你在 WSL 中需要走宿主机代理：

```bash
cp configs/env.example .env.local
```

然后编辑 `.env.local`，至少确认：

```bash
VLLM_PROXY_ENABLE=1
VLLM_PROXY_PORT=7897
```

如果你已经手动设置过 `HTTP_PROXY / HTTPS_PROXY / ALL_PROXY`，脚本会优先使用你已有的环境变量。

如果你不需要代理，也可以不创建 `.env.local`。

### Step 2: 安装或复用 vLLM 环境

```bash
bash scripts/setup_venv.sh
```

这个脚本默认复用仓库根目录的 `.venv`。如果 `.venv` 不存在，就会自动创建并安装：

- `vllm`
- 对应的 CUDA PyTorch wheel

### Step 3: 下载默认小模型

```bash
bash scripts/download_model.sh qwen2_5_0_5b_instruct
```

注意：

- 下载使用的是 Hugging Face 官方 `https://huggingface.co/<model>/resolve/main/...`
- 脚本采用直接 `GET` 下载文件，而不是依赖 `huggingface_hub` 的元数据探测
- 这样做是为了绕开当前 WSL + 代理环境里不稳定的 `HEAD` 请求

### Step 4: 运行离线 smoke test

```bash
bash scripts/run_offline_smoke.sh qwen2_5_0_5b_instruct
```

跑通后你应该能看到：

- `vLLM version`
- `PyTorch version`
- `CUDA available: True`
- 一条最终的 `OUTPUT: ...`

### Step 5: 启动本地服务

```bash
bash scripts/serve_local.sh qwen2_5_0_5b_instruct
```

默认服务地址：

- `http://127.0.0.1:8000`

脚本会自动：

- 后台启动 `vllm serve`
- 等待 `/health` 变为可用
- 把日志写到 `vllm_baseline/runtime/`

### Step 6: 做在线验证

```bash
bash scripts/verify_server.sh qwen2_5_0_5b_instruct
```

它会做两件事：

- 调用 `GET /v1/models`
- 通过 Python OpenAI client 调用 `POST /v1/chat/completions`

如果一切正常，你会看到：

- `/v1/models` 返回 `qwen2.5-0.5b-local`
- Python 客户端输出 `MODELS:` 和 `RESPONSE:`

### Step 7: 结束服务

```bash
bash scripts/stop_server.sh qwen2_5_0_5b_instruct
```

如果正常停止后你还怀疑端口被占用，可以再检查一次：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
```

如果输出不是 `000`，说明服务可能还在运行，此时可以先检查进程：

```bash
ps -ef | grep vllm
```

## 浏览器里会看到什么

很多同学第一次打开这些地址时会误以为“页面不正常”，其实下面这些现象都是正常的：

### 1. `/docs`

- 你会看到一个 `FastAPI / Swagger UI` 页面
- 页面里会列出 `/health`、`/v1/models`、`/v1/chat/completions` 等接口
- 这是接口文档页，不是聊天前端

### 2. `/health`

- 浏览器里经常看起来像“空白页”
- 这是正常的，因为它只是健康检查接口，不是网页内容页
- 这个接口的意义只是说明服务是否存活

更适合的检查方式：

```bash
curl http://127.0.0.1:8000/health
```

### 3. `/v1/models`

- 你会看到一段 JSON 文本
- 这也是正常的，因为它本来就是 API 返回值
- 如果能看到例如 `qwen2.5-0.5b-local`，说明模型已经加载成功

### 4. 为什么不是“聊天网页”？

因为 `vLLM` 默认提供的是：

- 模型推理服务
- OpenAI-compatible API
- Swagger 接口文档

它默认不提供类似 ChatGPT 的完整聊天网页 UI。

## 如何真正使用这个服务

### 1. 用 Swagger 页面手动测试

打开：

- `http://127.0.0.1:8000/docs`

然后在页面里找到：

- `/v1/models`
- `/v1/chat/completions`

点击 `Try it out` 后可以直接发请求。

`/v1/chat/completions` 的最小请求体示例：

```json
{
  "model": "qwen2.5-0.5b-local",
  "messages": [
    {
      "role": "user",
      "content": "用一句话解释什么是KV Cache。"
    }
  ],
  "temperature": 0.0,
  "max_tokens": 64
}
```

### 2. 用 curl 调用

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-0.5b-local",
    "messages": [
      {"role": "user", "content": "用一句话解释什么是KV Cache。"}
    ],
    "temperature": 0.0,
    "max_tokens": 64
  }'
```

### 3. 用 Python OpenAI 客户端

```bash
cd KVFabric/vllm_baseline
python examples/openai_client_smoke.py \
  --host 127.0.0.1 \
  --port 8000 \
  --model qwen2.5-0.5b-local \
  --prompt "用一句话解释什么是KV Cache。"
```

## 一条命令一条命令复现

给其他同学时，最实用的是下面这组命令：

```bash
cd KVFabric
cd vllm_baseline

cp configs/env.example .env.local
bash scripts/setup_venv.sh
bash scripts/download_model.sh qwen2_5_0_5b_instruct
bash scripts/run_offline_smoke.sh qwen2_5_0_5b_instruct
bash scripts/serve_local.sh qwen2_5_0_5b_instruct
bash scripts/verify_server.sh qwen2_5_0_5b_instruct
bash scripts/stop_server.sh qwen2_5_0_5b_instruct
```

## 可选模型：Qwen3 8B

如果你后续切到更大显存机器，可以使用：

```bash
bash scripts/download_model.sh qwen3_8b
bash scripts/run_offline_smoke.sh qwen3_8b
bash scripts/serve_local.sh qwen3_8b
bash scripts/verify_server.sh qwen3_8b
```

但请先确认资源：

- `Qwen/Qwen3-8B` 为多分片 safetensors
- 按官方模型卡信息，权重参数量约 `8B`
- 当前这台 `RTX 4070 Laptop GPU 8 GiB` 不应作为这个预设的主运行环境

建议额外准备：

- 至少 `20 GiB` 以上的可用显存或更高
- 更充足的磁盘空间用于多分片权重
- 更稳定的网络环境

## 脚本说明

### `scripts/setup_venv.sh`

- 创建或复用 Python 虚拟环境
- 安装 `vllm` 与对应 CUDA 依赖
- 打印 `vllm / torch / CUDA availability`

### `scripts/download_model.sh <preset>`

- 根据预设下载官方模型文件
- 支持断点续传与重试
- 已存在文件会自动跳过

### `scripts/run_offline_smoke.sh <preset>`

- 从本地模型目录加载模型
- 运行一次最小离线推理
- 由于 WSL 下 `vLLM` 使用 `spawn`，这里必须调用真实 `.py` 文件，而不是 stdin 脚本

### `scripts/serve_local.sh <preset>`

- 启动本地 OpenAI-compatible server
- 默认后台运行
- 自动写入 PID 文件和日志文件
- 默认把所有路径解释为相对仓库根目录的路径

### `scripts/verify_server.sh <preset>`

- 先验证 `/v1/models`
- 再用 `examples/openai_client_smoke.py` 做一次最小聊天请求

### `scripts/stop_server.sh <preset>`

- 按 PID 文件结束后台服务
- 这是推荐的标准结束方式
- 例如：

```bash
bash scripts/stop_server.sh qwen2_5_0_5b_instruct
```

## 基础使用示例

### 1. 查看模型列表

```bash
cd KVFabric/vllm_baseline
curl http://127.0.0.1:8000/v1/models
```

### 2. 直接调用聊天接口

```bash
cd KVFabric/vllm_baseline
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-0.5b-local",
    "messages": [
      {"role": "user", "content": "Reply with one short sentence about KV cache."}
    ],
    "temperature": 0.0,
    "max_tokens": 32
  }'
```

### 3. 使用 Python OpenAI 客户端

```bash
cd KVFabric/vllm_baseline
python examples/openai_client_smoke.py \
  --host 127.0.0.1 \
  --port 8000 \
  --model qwen2.5-0.5b-local
```

## 后续计划

当前这个工作区已经包含：

- 环境安装脚本
- 模型下载脚本
- offline smoke test
- online serving smoke test
- OpenAI-compatible API 验证脚本

后续还会继续补充：

- 更多自动化测试脚本
- 更完整的 benchmark / profiling 脚本
- 一个更方便直接使用的简单对话聊天 UI

## 常见问题

### 1. 为什么不用 `python - <<'PY'` 直接跑离线测试？

在 WSL 下，`vLLM` 会强制 `spawn` 多进程启动方式。此时如果主脚本来自 stdin，worker 进程会找不到真实脚本路径，从而报错。

因此这里统一使用：

- `examples/offline_smoke.py`
- `examples/openai_client_smoke.py`

### 2. 为什么下载脚本不用 `huggingface_hub`？

在当前环境中，官方 Hugging Face 页面和文件 `GET` 是可达的，但部分 `HEAD` 请求不稳定。为了让基线更稳，下载脚本直接对官方 `resolve/main` 路径做带重试的文件下载。

### 3. 为什么 `Qwen3-8B` 只是可选？

因为这个模型对显存和磁盘的要求明显更高。当前这套工作区的“默认能跑通基线”目标，是让更多同学先把 `Qwen/Qwen2.5-0.5B-Instruct` 跑起来，再继续做代码路径分析。

### 4. 现在这套内容能直接给别人用吗？

可以，前提是对方满足这些条件：

- 使用 Linux 或 WSL2
- 具备可用的 Python 3.12
- 如果走 GPU，能在系统里正常看到 NVIDIA 设备
- 如果需要代理，能在 `.env.local` 或 shell 环境中正确配置

### 5. 提交到 GitHub 前还需要注意什么？

提交前请确保仓库里没有这些本地内容：

- `.cache/`
- `.venv/`
- `vllm_baseline/.env.local`
- `vllm_baseline/runtime/*.log`
- `vllm_baseline/runtime/*.pid`

如果只提交脚本、profile、README 和 `.gitignore`，这套内容就是适合共享的。

因为它对显存要求明显更高。当前已知可稳定跑通的是 `Qwen/Qwen2.5-0.5B-Instruct` 这条小模型链路，适合作为本地 bring-up 基线。
