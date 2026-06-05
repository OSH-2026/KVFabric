# Ceph 与 Ray+Ceph 复现命令

## Docker 环境

本地启动 Docker Desktop 后拉取 Ceph 镜像：

```powershell
docker pull quay.io/ceph/daemon:latest-quincy
```

## Ceph 单 OSD

```powershell
powershell -ExecutionPolicy Bypass -File Lab4/scripts/run_ceph_single_node_docker.ps1
python Lab4/scripts/ceph_summarize_rados.py `
  --out Lab4/results/ceph/single_docker/rados_bench_summary.csv `
  Lab4/results/ceph/single_docker/rados_write_t1.txt `
  Lab4/results/ceph/single_docker/rados_seq_t1.txt `
  Lab4/results/ceph/single_docker/rados_rand_t1.txt `
  Lab4/results/ceph/single_docker/rados_write_t16.txt `
  Lab4/results/ceph/single_docker/rados_seq_t16.txt `
  Lab4/results/ceph/single_docker/rados_rand_t16.txt
```

## Ceph 多 OSD

```powershell
powershell -ExecutionPolicy Bypass -File Lab4/scripts/run_ceph_multi_osd_docker.ps1
python Lab4/scripts/ceph_summarize_rados.py `
  --out Lab4/results/ceph/multi_osd_docker/rados_bench_summary.csv `
  Lab4/results/ceph/multi_osd_docker/rados_write_t1.txt `
  Lab4/results/ceph/multi_osd_docker/rados_seq_t1.txt `
  Lab4/results/ceph/multi_osd_docker/rados_rand_t1.txt `
  Lab4/results/ceph/multi_osd_docker/rados_write_t16.txt `
  Lab4/results/ceph/multi_osd_docker/rados_seq_t16.txt `
  Lab4/results/ceph/multi_osd_docker/rados_rand_t16.txt
```

## Ray + Ceph

启动 live Ceph 容器：

```powershell
powershell -ExecutionPolicy Bypass -File Lab4/scripts/start_ceph_live_docker.ps1
```

本地 WSL 创建 Ray venv：

```bash
cd /home/qy-dream/OSH_Project/KVFabric
python3 -m venv Lab4/runtime/venvs/ray_ceph
. Lab4/runtime/venvs/ray_ceph/bin/activate
python -m pip install -U pip
python -m pip install ray==2.55.1
```

运行 Ray+Ceph 写入：

```bash
python Lab4/scripts/run_ray_ceph_store.py \
  --prompts Lab4/prompts/ray_batch_prompts.jsonl \
  --out-jsonl Lab4/results/ray_ceph/ray_ceph_store_c8.jsonl \
  --out-summary Lab4/results/ray_ceph/ray_ceph_store_c8_summary.csv \
  --payload-dir Lab4/results/ray_ceph/payloads \
  --container lab4-ceph-live \
  --pool lab4bench \
  --concurrency 8 \
  --limit 48
```

收集对象数和 Ceph 状态：

```powershell
docker exec lab4-ceph-live bash -lc "ceph -s > /lab4/results/ray_ceph/ceph_status_after_ray_store.txt"
docker exec lab4-ceph-live bash -lc "rados -p lab4bench ls | tee /lab4/results/ray_ceph/rados_ls_after_ray_store.txt | grep '^ray_ceph_' | wc -l > /lab4/results/ray_ceph/ray_ceph_object_count.txt"
docker rm -f lab4-ceph-live
```
