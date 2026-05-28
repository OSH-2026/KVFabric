# vLLM Performance Benchmark

> 可复现的 vLLM 标准基础服务性能测试流程。测量 Qwen3.5-2B 在不同输入/输出长度组合下的离线吞吐、GPU 显存使用与 Prefix Cache 影响。

[Chinese README (auto)](.) | [Methodology](docs/vllm_performance_benchmark_method.md) | [KV Cache Quality Benchmark](../kvcache_quality_benchmark/README.md)

## 目标

本项目是 KVFabric 论文复现工作的一部分，对应"王允 — vLLM 的标准基础服务性能评测"任务，回答三个核心问题：

1. vLLM 在普通 serving 场景下的性能区间是多少
2. 系统瓶颈主要在 prefill、decode、调度还是显存
3. 后续 KVCache 优化应优先降低首 token 延迟还是提升吞吐

## 目录结构

```
vllm_performance_benchmark/
├── README.md
├── configs/
│   ├── throughput_scan.json          # 吞吐扫描矩阵配置
│   └── qwen3_5_2b_perf_suite.json    # 测试套件配置
├── docs/
│   └── vllm_performance_benchmark_method.md
├── examples/
│   ├── offline_throughput_scan.py     # 核心评测脚本
│   └── summarize_perf_suite.py        # 跨 variant 汇总脚本
├── plans/
│   ├── qwen3_5_2b_baseline.env        # 基线单 variant 计划
│   └── qwen3_5_2b_prefix_ab.env       # Prefix cache A/B 对比计划
├── runs/
│   └── .gitkeep
├── scripts/
│   ├── common.sh                      # 共享函数
│   ├── run_perf_scan.sh               # 主入口（按 plan 执行）
│   ├── run_perf_variant.sh            # 单 variant 执行
│   ├── run_prefix_ab.sh               # Prefix cache A/B 快捷入口
│   ├── summarize_run.sh               # 查看单次运行摘要
│   └── summarize_suite.sh             # 汇总跨 variant 对比
└── variants/
    ├── vanilla.env                    # 官方 vLLM 基线
    └── prefix_on.env                  # Prefix caching 开启
```

## 快速开始

### 前置条件

```bash
# 1. 安装 vLLM 虚拟环境
cd KVFabric/vllm_baseline
bash scripts/setup_venv.sh

# 2. 下载模型
bash scripts/download_model.sh qwen3_5_2b
```

### 运行基线测试

```bash
cd KVFabric

# 运行基线吞吐扫描（一个 variant，约 30-50 分钟）
bash experiments/paper_reproductions/vllm_performance_benchmark/scripts/run_perf_scan.sh

# 运行 Prefix Cache A/B 对比（两个 variant，约 60-90 分钟）
bash experiments/paper_reproductions/vllm_performance_benchmark/scripts/run_prefix_ab.sh

# 查看某次运行的摘要
bash experiments/paper_reproductions/vllm_performance_benchmark/scripts/summarize_run.sh \
  experiments/paper_reproductions/vllm_performance_benchmark/runs/<run-dir>/vanilla_vllm
```

## 评测指标

| 指标 | 含义 | 来源 |
|------|------|------|
| Request Throughput | 每秒完成的推理请求数 (req/s) | `vllm bench throughput` 输出 |
| Total Token Throughput | 每秒处理的 input+output token 数 (tok/s) | 同上 |
| Output Token Throughput | 每秒生成的 token 数 (tok/s) | 同上 |
| KV Cache Usage % | KV Cache 使用率 | 引擎日志 `log-stats` |
| Prefix Cache Hit Rate % | 前缀缓存命中率 | 引擎日志 `log-stats` |
| KV Cache Memory | 可用的 KV Cache 显存 (GiB) | 引擎启动日志 |
| GPU Memory (model) | 模型权重显存占用 (GiB) | 引擎启动日志 |

### 关于 TTFT / TPOT / ITL

在线延迟指标（TTFT/TPOT/ITL）需要通过 `vllm bench serve` 对 HTTP 服务进行评测。当前脚本专注于**离线吞吐**，因为：

- `vllm bench serve` 在 WSL2 环境下因多进程 GPU IPC 限制不可用（所有请求返回 502）
- 在 bare-metal Linux / Docker 环境上可直接使用 `vllm bench serve` 并行评测在线延迟

## 自定义评测

### 调整扫描矩阵

编辑 `configs/throughput_scan.json`，修改 `scan_points` 数组：

```json
{
  "scan_points": [
    {"input_len": 128,  "output_len": 64,  "num_prompts": 100},
    {"input_len": 256,  "output_len": 128, "num_prompts": 80},
    {"input_len": 512,  "output_len": 256, "num_prompts": 50}
  ]
}
```

### 添加新 variant

1. 复制 `variants/vanilla.env` 为新文件
2. 修改 `SUITE_VARIANT_NAME` 和 `VARIANT_DESCRIPTION`
3. 创建新的 plan 或在已有 plan 的 `VARIANT_FILES` 数组中添加

### 更换模型

1. 在 `configs/` 中新建配套的 suite config
2. 在 `plans/` 中指定新的 `SUITE_CONFIG`
3. 在 variant 中指定对应的 `VARIANT_PRESET`（需在 `vllm_baseline/profiles/` 中存在）

## 输出结构

```text
runs/
└── 2026-04-27_143000_qwen3_5_2b_performance_suite/
    ├── vanilla_vllm/
    │   ├── config.json          # 扫描配置副本
    │   ├── env.json             # 环境信息
    │   ├── metrics.json         # 每个扫描点的指标
    │   └── summary.md           # 可读摘要
    ├── prefix_caching_on/       # （仅 A/B 对比时）
    │   └── ...
    ├── suite_summary.json       # 跨 variant 对比
    └── suite_summary.md         # 跨 variant 可读报告
```

## 计划文件（Plans）说明

| Plan 文件 | Variants | 用途 |
|-----------|----------|------|
| `qwen3_5_2b_baseline.env` | `vanilla.env`（仅基线） | 单 variant 快速扫描 |
| `qwen3_5_2b_prefix_ab.env` | `vanilla.env` + `prefix_on.env` | Prefix cache A/B 对比 |

## 限制与后续工作

- 当前仅支持离线吞吐（`vllm bench throughput`），在线延迟指标待 bare-metal Linux 环境验证
- 不支持多模型并行对比（需多 GPU），可在 plan 中添加多个 variant 并使用不同 preset
- KV Cache 压缩/量化 variant 需 vLLM 源码改动后才可加入
- 建议将结果与 [inference-perf](https://github.com/kubernetes-sigs/inference-perf) 对拍验证

## 参考

- [评测工具综合分析与使用指南](../../../docs/reports/first_test_report/wangyun/评测工具综合分析与使用指南.md)
- [Baseline Benchmark Report](../../../docs/reports/first_test_report/wangyun/benchmark_results/baseline_benchmark_report.md)
- [KVFabric Evaluation Plan](../../../docs/evaluation-plan.md)
- [vLLM Benchmark CLI](https://docs.vllm.ai/en/stable/benchmarking/cli/)
- [inference-perf](https://github.com/kubernetes-sigs/inference-perf)
