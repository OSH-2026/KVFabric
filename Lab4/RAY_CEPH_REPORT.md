# Ray + Ceph 联合拓展实验

小组成员：周家润、赵天翔、王允

## 目标

Ray 基础实验只统计推理请求延迟。为了把 Ray 调度和分布式存储结合起来，本实验增加一个联合任务：Ray 并发 task 将 48 条 prompt 的结构化对象写入 Ceph RADOS pool。

系统路径如下：

```text
Ray task
  -> 生成本地 payload 文件
  -> docker exec lab4-ceph-live rados put
  -> Ceph pool lab4bench
```

Ceph live 容器使用 3 个 OSD、pool size=2。Ray 在本地 WSL venv 中运行，容器通过 Docker Desktop 提供。

## 结果

| 指标 | 结果 |
| --- | ---: |
| Ray 并发 | 8 |
| 对象数 | 48 |
| 成功数 | 48 |
| 总耗时 | 7.633 s |
| 平均 put 延迟 | 0.631 s |
| P95 put 延迟 | 0.697 s |
| payload 总大小 | 8770 bytes |
| Ceph 中 `ray_ceph_` 对象数 | 48 |

Ceph 写入后的状态显示 3 个 OSD 均为 up/in，PG 为 active+clean。完整对象清单保存在 `results/ray_ceph/rados_ls_after_ray_store.txt`。

## 分析

这个实验验证了 Ray task 不仅可以调度推理请求，也可以作为批量对象写入的调度层。每条 prompt 被转换为一个独立对象写入 Ceph，最终 48 个对象全部成功。由于每个对象较小，主要开销来自 `docker exec` 和 RADOS 命令启动，而不是数据传输本身；如果改成长期运行的 Ceph 客户端进程或使用 RGW/S3 API，单对象写入延迟应该还能下降。

联合实验的意义在于把计算调度和存储系统连接起来：Ray 负责并发任务编排，Ceph 负责对象持久化和副本管理。这比单独展示 Ray 或 Ceph 更能体现分布式系统端到端链路。

完整结果见 `results/ray_ceph/`。
