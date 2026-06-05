# Ray 拓展实验

小组成员：周家润、赵天翔、王允

## 目标

原始 Ray 实验已经完成串行、round-robin 并发和 server-only 上界。拓展部分继续比较两种调度策略：

1. `weighted_static`：服务器 GPU 与本地 CPU endpoint 按 7:1 加权分配。
2. `latency_aware`：根据历史延迟和 inflight 数动态选择 endpoint，避免慢节点拖累整批任务。

实验仍使用 48 条 prompt，服务器 GPU endpoint 为 `server_gpu`，本地 WSL CPU endpoint 通过 SSH 反向隧道暴露为 `local_tunnel`。

## 结果

| 模式 | 策略 | 并发 | 成功数 | 总耗时 s | 平均延迟 s | P95 s | endpoint 分配 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 原始 round-robin | 等权轮询 | 4 | 34/48 | 121.60 | 5.64 | 21.12 | server/local 等权 |
| 原始 round-robin | 等权轮询 | 8 | 24/48 | 12.91 | 1.96 | 2.58 | 多数本地请求快速失败 |
| weighted 7:1 | 加权轮询 | 4 | 48/48 | 29.37 | 1.62 | 4.60 | server 42, local 6 |
| weighted 7:1 | 加权轮询 | 8 | 48/48 | 23.93 | 2.11 | 6.56 | server 42, local 6 |
| latency-aware | 动态延迟感知 | 4 | 48/48 | 19.86 | 1.13 | 1.40 | server 48 |
| latency-aware | 动态延迟感知 | 8 | 48/48 | 23.16 | 2.23 | 5.21 | server 43, local 5 |
| server-only 上界 | 只用服务器 GPU | 4 | 48/48 | 19.79 | 1.11 | 1.31 | server 48 |

## 分析

weighted 7:1 相比等权 round-robin 明显更稳定，原因是它只把少量请求分给本地 CPU endpoint，避免慢节点占用过多批量任务份额。latency-aware 在并发 4 下基本退化为选择服务器 GPU，结果接近 server-only 上界；这说明当前环境中本地 CPU endpoint 的性能不足以和服务器 GPU 等权协同。

这个结果补充说明：Ray 的价值不仅是并发执行，还包括调度策略。对异构节点做等权轮询会降低成功率；根据延迟调整分配比例，能在保证成功率的同时接近最快节点的吞吐上界。

完整结果见 `results/ray_extended/`。
