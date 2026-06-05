# Lab4 结果总览

## 产物清单

| 类别 | 文件 |
| --- | --- |
| 单机基线 | `results/single/baseline_short_summary.csv` |
| 参数矩阵 | `results/tuning/tuning_summary.csv` |
| 质量评估 | `results/quality/server_quality_summary.csv` |
| RPC | `results/rpc/rpc_gpu_local_cpu_summary.csv` |
| Ray | `results/ray/*_summary.csv`, `results/ray/*.jsonl` |
| Ray 拓展 | `results/ray_extended/*_summary.csv`, `results/ray_extended/*.jsonl` |
| Ceph | `results/ceph/*/rados_bench_summary.csv`, `results/ceph/*/ceph_status*.txt` |
| Ray + Ceph | `results/ray_ceph/ray_ceph_store_c8_summary.csv`, `results/ray_ceph/ceph_status_after_ray_store.txt` |

## 关键数字

| 实验 | 指标 | 结果 |
| --- | --- | ---: |
| 单机服务器 GPU | decode tok/s | 353.43 |
| 本地 CPU | decode tok/s | 44.11 |
| 参数矩阵最佳 decode | B/H 附近 | 356 tok/s |
| CPU-only 参数矩阵 | decode tok/s | 18.81 |
| RPC 多机 | decode tok/s | 9.92 |
| 质量评估 | 成功数 | 8/8 |
| Ray 串行 round-robin | 48 prompt 总耗时 | 216.08 s |
| Ray round-robin c2 | 48 prompt 总耗时 | 160.82 s |
| Ray server-only c4 | 48 prompt 总耗时 | 19.79 s |
| Ray server-only c8 | 48 prompt 总耗时 | 19.51 s |
| Ray latency-aware c4 | 48 prompt 总耗时 | 19.86 s |
| Ceph single write t1 | bandwidth | 227.96 MB/s |
| Ceph single write t16 | bandwidth | 306.27 MB/s |
| Ceph multi rand read t16 | bandwidth | 2433.31 MB/s |
| Ray + Ceph | 对象写入成功数 | 48/48 |

## 解释摘要

服务器 GPU 是稳定最快的后端。RPC 和 Ray 的本地 endpoint 都满足多机要求，但本地 CPU 与 SSH 反向隧道明显慢于服务器 GPU。Ray weighted 和 latency-aware 结果说明，异构节点不能简单等权轮询。Ceph Docker 实验完成了单 OSD 和 3 OSD 双副本测试，并通过提高客户端并发获得超过 20% 的写入吞吐提升。Ray + Ceph 联合实验进一步验证了 Ray task 可以并发写入 Ceph 对象池。
