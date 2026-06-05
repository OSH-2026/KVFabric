# AI 使用记录

小组成员：周家润、赵天翔、王允

## 使用范围

本次实验中 AI 主要用于：

1. 帮我核对 Lab4 要求，整理需要完成的实验项。
2. 在我确定实验机器和网络条件后，帮我检查 RPC、Ray 调度和 SSH 反向隧道方案是否可行。
3. `Lab4/scripts/` 下的实验脚本、解析脚本和汇总脚本由我编写和调整，AI 主要帮我检查参数、定位报错、解释日志，以及 debug 脚本里的解析问题。
4. 根据实际错误日志一起调整命令，例如用 `llama-completion` 替代新版 `llama-cli --no-conversation`，以及将 RPC 端口从非法的 `150052` 修正为 `15052`。
5. 帮我整理实验结果表格和报告结构，最后由我根据实际运行结果检查和修改。

## 人工确认

所有关键实验均实际运行并保留结果文件：

| 实验 | 证据 |
| --- | --- |
| 环境采集 | `ENVIRONMENT_SUMMARY.md` |
| 构建 | `ENVIRONMENT_SUMMARY.md`, 构建摘要 |
| 单机基线 | `results/single/baseline_short_summary.csv` |
| 参数矩阵 | `results/tuning/tuning_summary.csv` |
| 质量评估 | `results/quality/server_quality_summary.csv` |
| RPC | `results/rpc/rpc_gpu_local_cpu_summary.csv` |
| Ray | `results/ray/*_summary.csv` |
| Ray 拓展 | `results/ray_extended/*_summary.csv` |
| Ceph | `results/ceph/*/rados_bench_summary.csv` |
| Ray + Ceph | `results/ray_ceph/ray_ceph_store_c8_summary.csv` |

## 责任说明

AI 只作为辅助工具使用，主要用于排错、检查命令和整理文字。实验命令由我们在本地 WSL 和服务器上实际执行，最终结果以仓库内的 CSV/JSONL/Markdown 文件为准。敏感信息没有写入脚本或报告。
