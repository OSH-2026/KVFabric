# Ceph 实验报告

小组成员：周家润、赵天翔、王允

## 部署方式

Ceph 使用 Docker Desktop 本地运行，镜像为 `quay.io/ceph/daemon:latest-quincy`，Ceph 版本为 Quincy 17.2.7。由于镜像的 demo 入口缺少脚本，本实验改为在容器内手工初始化 monitor、manager 和 OSD：

1. 生成 `ceph.conf`、monmap、mon/admin/mgr/osd keyring。
2. 启动 `ceph-mon`、`ceph-mgr` 和 `ceph-osd`。
3. 创建 `lab4bench` pool。
4. 使用 `rados bench` 测量写入、顺序读和随机读。

本实验完成两组 Ceph Docker 配置：

| 配置 | OSD 数 | pool size | 说明 |
| --- | ---: | ---: | --- |
| single_docker | 1 | 1 | 单 OSD 基线，用于观察基础 rados 性能 |
| multi_osd_docker | 3 | 2 | 3 OSD + 双副本，模拟更接近分布式存储的副本写入 |

## 指标

实际记录了以下指标：

| 指标 | 来源 |
| --- | --- |
| 集群健康状态 | `ceph -s` |
| OSD 拓扑 | `ceph osd tree` |
| OSD 使用量 | `ceph osd df` |
| PG 状态 | `ceph pg stat` |
| OSD 内部 bench | `ceph tell osd.0 bench` |
| write bandwidth / IOPS / latency | `rados bench write` |
| sequential read bandwidth / IOPS / latency | `rados bench seq` |
| random read bandwidth / IOPS / latency | `rados bench rand` |

## 单 OSD 结果

| 操作 | 线程 | 带宽 MB/s | IOPS | 平均延迟 s |
| --- | ---: | ---: | ---: | ---: |
| write | 1 | 227.96 | 56 | 0.0175 |
| write | 16 | 306.27 | 76 | 0.2083 |
| seq read | 1 | 690.06 | 172 | 0.0054 |
| seq read | 16 | 1400.67 | 350 | 0.0450 |
| rand read | 1 | 786.62 | 196 | 0.0047 |
| rand read | 16 | 1452.38 | 363 | 0.0436 |

单 OSD 下，写入从 227.96 MB/s 提升到 306.27 MB/s，提升约 34.4%；顺序读和随机读也分别超过 1000 MB/s。

## 多 OSD 结果

| 操作 | 线程 | 带宽 MB/s | IOPS | 平均延迟 s |
| --- | ---: | ---: | ---: | ---: |
| write | 1 | 134.92 | 33 | 0.0296 |
| write | 16 | 178.57 | 44 | 0.3551 |
| seq read | 1 | 688.86 | 172 | 0.0054 |
| seq read | 16 | 2423.50 | 605 | 0.0255 |
| rand read | 1 | 701.92 | 175 | 0.0053 |
| rand read | 16 | 2433.31 | 608 | 0.0257 |

multi_osd_docker 使用 3 个 OSD 和 size=2 副本。写入吞吐低于 single_docker，因为每个对象需要写两份副本；但线程数从 1 提高到 16 后，写入吞吐仍提升约 32.3%。读性能在 16 线程下提升明显，顺序读和随机读均达到约 2.4 GB/s。

## 结论

Ceph 的性能和 pool 副本策略、OSD 数、客户端并发度直接相关。单副本配置更快但不具备副本可靠性；双副本配置写入变慢，但更接近真实分布式存储场景。客户端并发是本实验最直接有效的优化项，单 OSD 和多 OSD 写入均超过 20% 提升。

完整结果见 `results/ceph/`。
