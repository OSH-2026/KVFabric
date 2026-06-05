# OSH 2026 Lab4 实验报告

小组成员：周家润、赵天翔、王允

本目录保存 Lab4 的最终提交材料。新增脚本、prompt、结果摘要和报告都放在 `Lab4/` 下。

## 实验目标

本实验完成 llama.cpp 主线任务，并额外完成 Ray、Ceph 及 Ray+Ceph 联合拓展：

1. 使用 GGUF 量化模型完成 llama.cpp 单机推理部署。
2. 设计并实际测量 6 类以上性能指标。
3. 对 10 组 llama.cpp 参数配置做重复测试和分析。
4. 使用 8 条 prompt 做输出质量评估。
5. 完成服务器主机 + 本地从机的 RPC 多机推理，并与单机推理对比。
6. 使用 Ray 调度 48 条批量 prompt，对比串行、Ray 并发、双 endpoint round-robin 和 server-only 上界。
7. 增加 Ray weighted 与 latency-aware 调度策略，比较异构慢节点下的调度效果。
8. 使用 Docker 部署 Ceph，完成单 OSD 和 3 OSD 双副本 RADOS bench。
9. 完成 Ray+Ceph 联合实验：Ray 并发 task 将 48 个对象写入 Ceph RADOS pool。

## 环境与模型

| 角色 | 环境 | 用途 |
| --- | --- | --- |
| 服务器 `robowalker` | Ubuntu 24.04.4, Xeon Silver 4216, 187 GiB RAM, 2 x RTX 3090 | 单机 GPU 推理、RPC 主机、Ray 调度端、server GPU endpoint |
| 本地 WSL | Ubuntu 24.04.1, i7-14650HX, 15 GiB RAM, RTX 4070 Laptop 可见 | RPC 从机、本地 CPU llama-server endpoint |

模型使用 `Qwen/Qwen2.5-1.5B-Instruct-GGUF` 的 `qwen2.5-1.5b-instruct-q4_k_m.gguf`，本地和服务器模型 SHA256 均为：

```text
6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
```

llama.cpp 两端均使用 commit:

```text
06938ac129e5feee1e731323e5c37dc973de5573
```

## 单机基线

短 prompt 重复 5 次的平均结果如下：

| 模式 | load ms | prompt tok/s | decode tok/s | total ms | max RSS KiB | wall s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 服务器 GPU | 573.33 | 1351.80 | 353.43 | 223.54 | 1426480 | 1.92 |
| 本地 CPU | 936.63 | 180.15 | 44.11 | 1566.15 | 1822771 | 2.91 |

结论：服务器 GPU decode 吞吐约为本地 CPU 的 8.0 倍，是主线性能测试和 Ray server-only 上界的主要计算资源。

## 参数优化

共测试 10 组配置，每组 5 次。核心结果：

| 配置 | 说明 | decode tok/s | load ms | wall s |
| --- | --- | ---: | ---: | ---: |
| A | GPU, threads=8, ctx=2048 | 351.38 | 573.03 | 1.91 |
| B | GPU, threads=4 | 356.00 | 572.37 | 1.87 |
| C | GPU, threads=16 | 353.38 | 581.40 | 1.88 |
| F | GPU, ctx=4096 | 353.56 | 574.81 | 1.86 |
| H | GPU, no-mmap | 356.30 | 513.14 | 1.82 |
| G | CPU-only | 18.81 | 1076.21 | 6.00 |

在该 1.5B Q4 模型和短 prompt 下，GPU 配置的 decode 吞吐集中在约 350 tok/s；线程数、batch size、ctx-size 对短生成吞吐影响较小。CPU-only 配置显著慢于 GPU。`--no-mmap` 在短任务中降低了 RSS 统计值和加载时间，但它改变了加载/内存映射行为，不能简单推广为所有任务的最优配置。

完整数据见 [results/tuning/tuning_summary.csv](results/tuning/tuning_summary.csv)。

## 质量评估

8 条质量 prompt 全部在服务器 GPU 上成功完成：

| 指标 | 结果 |
| --- | ---: |
| prompt 数 | 8 |
| 成功数 | 8 |
| 平均 wall time | 2.41 s |
| decode tok/s 范围 | 364.78 - 374.35 |
| 输出字符数范围 | 2215 - 2418 |

本次质量评估主要检查回答是否对应题目、是否明显跑题或重复，以及输出格式是否可读。运行时 8 条 prompt 都正常返回，没有出现失败退出；由于完整输出较长，提交中只保留 prompt、运行脚本和统计摘要。

完整摘要见 [results/quality/server_quality_summary.csv](results/quality/server_quality_summary.csv)。

## RPC 多机推理

RPC 采用服务器为主机、本地 WSL 为从机：

```text
server llama-completion --rpc 127.0.0.1:15052
  -> SSH reverse tunnel
  -> local rpc-server 127.0.0.1:50052
```

调试时发现原来使用过的 `150052` 超过了 TCP/UDP 端口上限，实际实验改为合法端口 `15052`。

RPC 重复 5 次结果：

| 模式 | load ms | prompt tok/s | decode tok/s | total ms | wall s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 单机服务器 GPU | 573.33 | 1351.80 | 353.43 | 223.54 | 1.92 |
| RPC: 服务器 GPU + 本地 CPU 从机 | 67688.82 | 17.35 | 9.92 | 8476.26 | 99.34 |

结论：本实验中的 RPC 链路满足多机推理要求，但性能明显低于单机 GPU。主要原因是本地从机为 CPU 后端，且通过 SSH 反向隧道通信，模型加载和推理中引入大量远程后端同步、网络转发和慢节点开销。这个结果符合预期，说明 RPC 的价值不等于在异构弱从机上自动加速。

完整数据见 [results/rpc/rpc_gpu_local_cpu_summary.csv](results/rpc/rpc_gpu_local_cpu_summary.csv)。

## Ray 批量调度

Ray 在服务器上运行，调度两个 HTTP endpoint：

| endpoint | URL | 后端 |
| --- | --- | --- |
| `server_gpu` | `http://127.0.0.1:18080` | 服务器 llama-server GPU |
| `local_tunnel` | `http://127.0.0.1:18081` | SSH 反向隧道到本地 CPU llama-server |

使用 48 条 prompt，结果如下：

| 模式 | endpoint 策略 | 并发 | 请求数 | 成功数 | 总耗时 s | 平均延迟 s | P95 s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| serial_round_robin | server/local 轮询串行 | 1 | 48 | 48 | 216.08 | 4.50 | 10.70 |
| ray_round_robin_c2 | server/local 轮询 | 2 | 48 | 48 | 160.82 | 6.40 | 16.76 |
| ray_round_robin_c4 | server/local 压力档 | 4 | 48 | 34 | 121.60 | 5.64 | 21.12 |
| ray_round_robin_c8 | server/local 压力档 | 8 | 48 | 24 | 12.91 | 1.96 | 2.58 |
| ray_server_only_c4 | 只打服务器 GPU | 4 | 48 | 48 | 19.79 | 1.11 | 1.31 |
| ray_server_only_c8 | 只打服务器 GPU | 8 | 48 | 48 | 19.51 | 2.09 | 2.59 |

结论：

1. Ray 并发 2 的 round-robin 比串行 round-robin 更快，总耗时从 216.08 s 降到 160.82 s，说明任务级并发有效。
2. round-robin 并发 4/8 暴露了本地 CPU endpoint 与 SSH 反向隧道的稳定性瓶颈，成功率下降，不能作为最优配置，只作为压力测试证据。
3. server-only 并发 4/8 均为 48/48 成功，总耗时约 19.5-19.8 s，说明 Ray 调度和服务器 GPU endpoint 本身稳定；整体瓶颈来自慢节点和隧道，而不是 Ray 本身。
4. 如果继续优化调度策略，可以考虑 latency-aware 或 weighted scheduling，减少分配给本地 CPU 慢节点的请求比例。

完整数据见 [results/ray/](results/ray/)。

## Ray 调度拓展

在原始 Ray 结果基础上，继续测试 weighted 7:1 和 latency-aware 两种调度策略：

| 模式 | 策略 | 并发 | 成功数 | 总耗时 s | 平均延迟 s | P95 s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 原始 round-robin | 等权轮询 | 4 | 34/48 | 121.60 | 5.64 | 21.12 |
| weighted 7:1 | 加权轮询 | 4 | 48/48 | 29.37 | 1.62 | 4.60 |
| latency-aware | 动态延迟感知 | 4 | 48/48 | 19.86 | 1.13 | 1.40 |
| server-only 上界 | 只打服务器 GPU | 4 | 48/48 | 19.79 | 1.11 | 1.31 |

latency-aware 在当前异构环境中基本选择服务器 GPU，结果接近 server-only 上界，说明等权 round-robin 不适合性能差距很大的节点。完整数据见 [results/ray_extended/](results/ray_extended/) 和 [RAY_EXTENDED_REPORT.md](RAY_EXTENDED_REPORT.md)。

## Ceph Docker 实验

Ceph 使用 `quay.io/ceph/daemon:latest-quincy` 镜像在本地 Docker Desktop 中运行。完成了单 OSD 和 3 OSD 两组 RADOS bench：

| 配置 | OSD 数 | pool size | 操作 | 线程 | 带宽 MB/s | IOPS | 平均延迟 s |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| single_docker | 1 | 1 | write | 1 | 227.96 | 56 | 0.0175 |
| single_docker | 1 | 1 | write | 16 | 306.27 | 76 | 0.2083 |
| multi_osd_docker | 3 | 2 | write | 1 | 134.92 | 33 | 0.0296 |
| multi_osd_docker | 3 | 2 | write | 16 | 178.57 | 44 | 0.3551 |
| multi_osd_docker | 3 | 2 | rand read | 16 | 2433.31 | 608 | 0.0257 |

单 OSD 写入并发优化提升约 34.4%，3 OSD 双副本写入并发优化提升约 32.3%。完整数据见 [results/ceph/](results/ceph/) 和 [CEPH_REPORT.md](CEPH_REPORT.md)。

## Ray + Ceph 联合实验

Ray 在本地 WSL venv 中运行，Ceph 使用 3 OSD live Docker 容器。48 个 Ray task 并发写入 Ceph RADOS pool：

| 指标 | 结果 |
| --- | ---: |
| Ray 并发 | 8 |
| 对象数 | 48 |
| 成功数 | 48 |
| 总耗时 | 7.633 s |
| 平均 put 延迟 | 0.631 s |
| P95 put 延迟 | 0.697 s |

该实验验证了 Ray 可以作为批量对象写入调度层，Ceph 负责对象持久化和副本管理。完整数据见 [results/ray_ceph/](results/ray_ceph/) 和 [RAY_CEPH_REPORT.md](RAY_CEPH_REPORT.md)。

## 目录说明

| 路径 | 内容 |
| --- | --- |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 构建、模型、服务和实验命令 |
| [DEPLOYMENT_CEPH.md](DEPLOYMENT_CEPH.md) | Ceph 与 Ray+Ceph 复现命令 |
| [PERFORMANCE_ANALYSIS.md](PERFORMANCE_ANALYSIS.md) | 性能分析与系统解释 |
| [RAY_EXTENDED_REPORT.md](RAY_EXTENDED_REPORT.md) | Ray 调度策略拓展 |
| [CEPH_REPORT.md](CEPH_REPORT.md) | Ceph Docker 部署与性能实验 |
| [RAY_CEPH_REPORT.md](RAY_CEPH_REPORT.md) | Ray + Ceph 联合实验 |
| [AI_USAGE.md](AI_USAGE.md) | AI 辅助记录 |
| [ENVIRONMENT_SUMMARY.md](ENVIRONMENT_SUMMARY.md) | 环境、构建、模型摘要 |
| [results/RESULT_OVERVIEW.md](results/RESULT_OVERVIEW.md) | 关键结果总览 |
| [scripts/](scripts/) | 可复现实验脚本 |
| [prompts/](prompts/) | 质量评估和 Ray 批量 prompt |

`runtime/`、模型、源码树、venv、PID、日志和大构建产物均被 `.gitignore` 排除。
