# Lab4 部署与复现命令

以下命令记录本次实验使用的主要流程。敏感信息、密码、私钥和 token 均未写入仓库。

## 目录

本地：

```bash
cd /home/qy-dream/OSH_Project/KVFabric
mkdir -p Lab4/{configs,prompts,scripts,results,runtime}
```

服务器：

```bash
ssh robowalker 'mkdir -p ~/KVFabric_Lab4_runtime/{src,models,logs,results,prompts,scripts,configs}'
```

## llama.cpp

服务器 CUDA + RPC：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime/src
  test -d llama.cpp || git clone https://github.com/ggml-org/llama.cpp
  cd llama.cpp
  git checkout 06938ac129e5feee1e731323e5c37dc973de5573
  cmake -S . -B build-cuda-rpc -DGGML_CUDA=ON -DGGML_RPC=ON
  cmake --build build-cuda-rpc --config Release -j "$(nproc)"
'
```

本地 CPU + RPC：

```bash
cd /home/qy-dream/OSH_Project/KVFabric/Lab4/runtime/src
test -d llama.cpp || git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
git checkout 06938ac129e5feee1e731323e5c37dc973de5573
cmake -S . -B build-cpu-rpc -DGGML_RPC=ON
cmake --build build-cpu-rpc --config Release -j "$(nproc)"
```

## 模型

本地下载：

```bash
cd /home/qy-dream/OSH_Project/KVFabric
curl -L --continue-at - \
  -o Lab4/runtime/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
ln -sf qwen2.5-1.5b-instruct-q4_k_m.gguf Lab4/runtime/models/model.gguf
sha256sum Lab4/runtime/models/model.gguf
```

服务器外网访问 Hugging Face 不稳定时，使用本地 HTTP 服务 + SSH 反向隧道传输模型。本次两端模型 SHA256 一致：

```text
6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
```

## 单机和调参

短 prompt 重复测试：

```bash
bash Lab4/scripts/run_completion_repeats.sh \
  Lab4/runtime/src/llama.cpp/build-cpu-rpc/bin/llama-completion \
  Lab4/runtime/models/model.gguf \
  Lab4/prompts/single_short.txt \
  Lab4/results/single/baseline_local_cpu_short \
  5 local_cpu_short --n-gpu-layers 0
```

服务器调参矩阵：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime
  RUNS=5 bash scripts/run_server_tuning_matrix.sh
'
```

日志解析：

```bash
python3 Lab4/scripts/parse_completion_logs.py \
  --label server_gpu_short \
  --out Lab4/results/single/server_gpu_short.csv \
  Lab4/results/server/baseline_gpu_short/run_*.log

python3 Lab4/scripts/summarize_completion_csv.py \
  --out Lab4/results/single/baseline_short_summary.csv \
  Lab4/results/single/server_gpu_short.csv \
  Lab4/results/single/local_cpu_short.csv
```

## RPC

本地启动 RPC server：

```bash
cd /home/qy-dream/OSH_Project/KVFabric
bash Lab4/scripts/start_local_rpc_server.sh
```

建立反向隧道：

```bash
ssh -N -R 15052:127.0.0.1:50052 robowalker
```

服务器 RPC 推理：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime
  ./src/llama.cpp/build-cuda-rpc/bin/llama-completion \
    -m ./models/model.gguf \
    -f ./prompts/single_rpc.txt \
    -n 64 -no-cnv \
    --threads 8 --ctx-size 2048 --temp 0.2 --no-display-prompt \
    --rpc 127.0.0.1:15052 \
    --n-gpu-layers 99
'
```

## Ray

服务器安装 Ray。由于服务器没有 sudo 且缺少 `python3-venv`，本次使用用户级安装：

```bash
ssh robowalker 'python3 -m pip install --user --break-system-packages ray[default] requests'
```

启动服务器 GPU endpoint：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime
  env ROOT=$HOME/KVFabric_Lab4_runtime \
      BIN=$HOME/KVFabric_Lab4_runtime/src/llama.cpp/build-cuda-rpc/bin/llama-server \
      MODEL=$HOME/KVFabric_Lab4_runtime/models/model.gguf \
      HOST=127.0.0.1 PORT=18080 THREADS=8 CTX_SIZE=4096 PARALLEL=4 \
      LOG=$HOME/KVFabric_Lab4_runtime/results/ray/server_llama_server_18080.log \
      PID_FILE=$HOME/KVFabric_Lab4_runtime/logs/server_llama_server_18080.pid \
      bash scripts/start_llama_server_bg.sh --n-gpu-layers 99
'
```

启动本地 CPU endpoint：

```bash
cd /home/qy-dream/OSH_Project/KVFabric
env ROOT=/home/qy-dream/OSH_Project/KVFabric \
    BIN=/home/qy-dream/OSH_Project/KVFabric/Lab4/runtime/src/llama.cpp/build-cpu-rpc/bin/llama-server \
    MODEL=/home/qy-dream/OSH_Project/KVFabric/Lab4/runtime/models/model.gguf \
    HOST=127.0.0.1 PORT=18081 THREADS=8 CTX_SIZE=2048 PARALLEL=2 \
    LOG=/home/qy-dream/OSH_Project/KVFabric/Lab4/results/ray/local_llama_server_18081.log \
    PID_FILE=/home/qy-dream/OSH_Project/KVFabric/Lab4/runtime/logs/local_llama_server_18081.pid \
    bash Lab4/scripts/start_llama_server_bg.sh --n-gpu-layers 0
```

建立本地 endpoint 反向隧道：

```bash
ssh -N -R 18081:127.0.0.1:18081 robowalker
```

探活：

```bash
ssh robowalker 'curl -fsS http://127.0.0.1:18080/health; curl -fsS http://127.0.0.1:18081/health'
```

运行 Ray 批量：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime
  python3 scripts/run_ray_batch.py \
    --prompts prompts/ray_batch_prompts.jsonl \
    --endpoints configs/endpoints.json \
    --out-jsonl results/ray/serial_round_robin.jsonl \
    --out-summary results/ray/serial_round_robin_summary.csv \
    --label serial_round_robin \
    --mode serial \
    --endpoint-policy round_robin \
    --timeout 240
'
```

并发压力：

```bash
ssh robowalker 'cd ~/KVFabric_Lab4_runtime && bash scripts/run_ray_suite.sh'
```

server-only 上界：

```bash
ssh robowalker '
  cd ~/KVFabric_Lab4_runtime
  python3 scripts/run_ray_batch.py \
    --prompts prompts/ray_batch_prompts.jsonl \
    --endpoints configs/endpoints.json \
    --out-jsonl results/ray/ray_server_only_c4.jsonl \
    --out-summary results/ray/ray_server_only_c4_summary.csv \
    --label ray_server_only_c4 \
    --mode ray \
    --endpoint-policy server_only \
    --concurrency 4 \
    --timeout 240
'
```
