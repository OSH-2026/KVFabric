# Lab4 性能分析

## 指标定义

本实验实际测量了以下指标：

| 指标 | 来源 | 含义 |
| --- | --- | --- |
| `load_time_ms` | llama.cpp `common_perf_print` | 模型加载和初始化耗时 |
| `prompt_tok_s` | llama.cpp `prompt eval time` | prefill 阶段吞吐 |
| `eval_tok_s` | llama.cpp `eval time` | decode 阶段吞吐 |
| `total_time_ms` | llama.cpp `total time` | 单次生成内部总耗时 |
| `elapsed_s` | `/usr/bin/time -v` | 端到端 wall time |
| `max_rss_kb` | `/usr/bin/time -v` | 进程最大常驻内存 |
| `success` | Ray HTTP 调用结果 | 请求成功数 |
| `p50/p95_latency_s` | Ray 脚本统计 | 批量请求尾延迟 |

## 单机与 CPU 对比

| 模式 | decode tok/s | prompt tok/s | wall s | 解释 |
| --- | ---: | ---: | ---: | --- |
| 服务器 GPU | 353.43 | 1351.80 | 1.92 | CUDA 后端承担主要矩阵计算 |
| 本地 CPU | 44.11 | 180.15 | 2.91 | CPU-only，decode 吞吐约为 GPU 的 12.5% |

GPU 对 decode 阶段收益最明显。prefill 阶段也有明显差异，但短 prompt 下 wall time 还受加载、进程启动和缓存状态影响。

## 参数矩阵

| 配置 | 关键参数 | decode tok/s | stdev | 结论 |
| --- | --- | ---: | ---: | --- |
| A | GPU, t=8, ctx=2048 | 351.38 | 2.48 | 基线稳定 |
| B | GPU, t=4, ctx=2048 | 356.00 | 7.91 | 与 t=8 接近，GPU 主导时线程数不是主瓶颈 |
| C | GPU, t=16, ctx=2048 | 353.38 | 6.25 | 增加线程数没有明显收益 |
| D | batch=256 | 350.66 | 4.44 | batch 变化对短 decode 影响有限 |
| E | batch=512 | 350.84 | 1.21 | 稳定但没有显著提升 |
| F | ctx=4096 | 353.56 | 5.11 | 短 prompt 下 ctx 增大未明显降低吞吐 |
| G | CPU-only | 18.81 | 5.20 | 显著慢于 GPU |
| H | no-mmap | 356.30 | 6.99 | 短任务下加载/RSS 表现好，但需结合场景判断 |
| I | batch=1024 | 353.55 | 7.62 | 与基线接近 |
| J | ctx=8192 | 353.31 | 4.00 | 短 prompt 下仍接近基线 |

主要结论：该模型和任务规模较小，GPU decode 阶段稳定在约 350 tok/s；CPU-only 是唯一明显性能断崖。优化优先级应先保证 GPU offload，再考虑线程、ctx-size、batch-size 的细调。

## RPC 分析

| 模式 | decode tok/s | load ms | wall s | 成功数 |
| --- | ---: | ---: | ---: | ---: |
| 单机 GPU | 353.43 | 573.33 | 1.92 | 5/5 |
| RPC GPU + 本地 CPU | 9.92 | 67688.82 | 99.34 | 5/5 |

RPC 结果说明：

1. 多机链路可用，本地 `rpc-server` 日志出现多次连接，远端 `--rpc 127.0.0.1:15052` 推理成功。
2. 服务器 GPU 与本地 CPU 是强异构组合，模型层或张量分配到本地 CPU 后拖慢整体。
3. SSH 反向隧道增加连接、加载和数据传输开销。
4. RPC 更适合性能接近、网络稳定、后端算力能互补的多机环境；本实验重点是完成和分析多机 RPC，而不是证明异构慢节点加速。

## Ray 分析

| 模式 | 成功率 | 总耗时 s | 平均延迟 s | P95 s | 解释 |
| --- | ---: | ---: | ---: | ---: | --- |
| serial_round_robin | 48/48 | 216.08 | 4.50 | 10.70 | 串行等待本地慢节点 |
| ray_round_robin_c2 | 48/48 | 160.82 | 6.40 | 16.76 | 并发 2 改善总耗时，但慢节点拉高延迟 |
| ray_round_robin_c4 | 34/48 | 121.60 | 5.64 | 21.12 | 压力档，本地隧道开始失败 |
| ray_round_robin_c8 | 24/48 | 12.91 | 1.96 | 2.58 | 多数本地请求快速失败，不能看作有效加速 |
| ray_server_only_c4 | 48/48 | 19.79 | 1.11 | 1.31 | 服务器 GPU 上界，稳定 |
| ray_server_only_c8 | 48/48 | 19.51 | 2.09 | 2.59 | 更高并发下延迟上升但吞吐稳定 |

Ray 的价值体现在批量任务调度，而不是单个 prompt 加速。两端 round-robin 在并发 2 时有效，但当并发升高，本地 CPU endpoint 和 SSH 隧道成为明显瓶颈。server-only 结果证明 Ray runtime 和服务器 GPU 服务可以稳定承载 48 条 prompt；失败来自异构慢节点与隧道稳定性。

后续改进：

1. 性能差距很大的节点不适合直接做等权 round-robin。
2. 可以尝试 weighted round-robin 或 latency-aware 调度，根据历史延迟动态降低慢节点权重。
3. 对本地/隧道 endpoint 设置并发上限和熔断策略，避免失败请求影响整批统计。
4. 如果目标是真正提升总吞吐，更合理的做法是增加同级 GPU endpoint，而不是混入 CPU 慢节点。

## Ceph 分析

| 配置 | 操作 | 线程 | 带宽 MB/s | IOPS | 平均延迟 s |
| --- | --- | ---: | ---: | ---: | ---: |
| single_docker | write | 1 | 227.96 | 56 | 0.0175 |
| single_docker | write | 16 | 306.27 | 76 | 0.2083 |
| multi_osd_docker | write | 1 | 134.92 | 33 | 0.0296 |
| multi_osd_docker | write | 16 | 178.57 | 44 | 0.3551 |
| multi_osd_docker | seq read | 16 | 2423.50 | 605 | 0.0255 |
| multi_osd_docker | rand read | 16 | 2433.31 | 608 | 0.0257 |

Ceph 的主要优化变量是客户端并发度和副本配置。单 OSD 下，写入从 227.96 MB/s 提升到 306.27 MB/s，提升约 34.4%；3 OSD 双副本下，写入从 134.92 MB/s 提升到 178.57 MB/s，提升约 32.3%。multi_osd_docker 写入低于 single_docker，是因为 pool size=2 带来副本写放大；但读操作可以从多 OSD 并发中受益，16 线程随机读达到 2433.31 MB/s。

## Ray + Ceph 分析

Ray + Ceph 联合实验中，48 个 Ray task 全部成功写入 Ceph RADOS pool，总耗时 7.633 s，平均 `rados put` 延迟 0.631 s，P95 为 0.697 s。当前实现每个 task 都通过 `docker exec` 调用一次 `rados`，因此延迟主要来自进程启动和容器命令调用；如果改成常驻客户端或 RGW/S3 API，存储写入部分仍有继续优化空间。
