# Lab4 环境与构建摘要

根 `.gitignore` 中的 `env/` 会忽略 `Lab4/results/env/`，因此这里保留可提交的环境摘要。

## 本地 WSL

| 项目 | 值 |
| --- | --- |
| hostname | `QYdream` |
| OS | Ubuntu 24.04.1 LTS on WSL2 |
| kernel | `6.6.87.2-microsoft-standard-WSL2` |
| CPU | Intel Core i7-14650HX, 24 logical CPUs |
| memory | 15 GiB |
| Python | 3.12.3 |
| CMake | 3.28.3 |
| GCC/G++ | 13.3.0 |
| visible GPU | NVIDIA RTX 4070 Laptop, 8 GiB |
| llama.cpp build | CPU + RPC |

## 服务器

| 项目 | 值 |
| --- | --- |
| hostname | `rm123-WS-C621E-SAGE-Series` |
| OS | Ubuntu 24.04.4 LTS |
| kernel | `6.17.0-29-generic` |
| CPU | 2 x Intel Xeon Silver 4216, 64 logical CPUs |
| memory | 187 GiB |
| Python | 3.12.3 |
| CMake | 3.28.3 |
| GCC/G++ | 13.3.0 |
| CUDA toolkit | 12.0 |
| GPU | 2 x NVIDIA RTX 3090, 24 GiB each |
| llama.cpp build | CUDA + RPC |

## 版本和模型

| 项目 | 值 |
| --- | --- |
| llama.cpp commit | `06938ac129e5feee1e731323e5c37dc973de5573` |
| model | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` |
| file | `qwen2.5-1.5b-instruct-q4_k_m.gguf` |
| SHA256 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` |

## 构建产物

| 机器 | 二进制 |
| --- | --- |
| 本地 | `build-cpu-rpc/bin/llama-cli`, `llama-server`, `rpc-server` |
| 服务器 | `build-cuda-rpc/bin/llama-cli`, `llama-server`, `rpc-server` |

## 环境限制

1. 服务器没有 sudo 权限，Ray 使用 `python3 -m pip install --user --break-system-packages ray[default] requests` 安装到用户目录。
2. 本地 WSL 在 NAT 后面，RPC 和 Ray 的本地 endpoint 均通过 SSH 反向隧道暴露给服务器。
3. RPC 实际端口为 `15052`，因为 `150052` 超过 TCP/UDP 端口上限。
