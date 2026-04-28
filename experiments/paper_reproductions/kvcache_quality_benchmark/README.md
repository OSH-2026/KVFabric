# KVCache Quality Benchmark

本目录用于承接 `/work` 中“3. KVCache 压缩与质量评测”的复现与后续扩展。

目标不是直接宣称已经实现了某种 KV 压缩算法，而是先把这一条实验线搭成一套完整、通用、可扩展的测试流程，使后续无论接入：

- KV 裁剪
- KV 量化
- selective keep / eviction
- block 压缩或重排

都能沿用同一套任务集、运行入口、打分口径和汇总输出。

## 目录结构

```text
kvcache_quality_benchmark/
├─ README.md
├─ configs/
├─ docs/
├─ examples/
├─ plans/
├─ runs/
├─ scripts/
└─ variants/
```

各目录职责如下：

- `configs/`
  质量评测套件配置与任务集定义。

- `docs/`
  方法说明、任务清单、后续接入建议。

- `examples/`
  Python 评测与汇总脚本。

- `plans/`
  一次 suite 运行需要跑哪些 variant 的计划文件。

- `runs/`
  真实运行输出。

- `scripts/`
  Shell 入口脚本。

- `variants/`
  不同候选方案的配置。

## 当前设计原则

这套流程把“质量评测”拆成两部分：

1. 任务质量：看输出是否偏离预期。
2. 性能代价：看推理速度、token 吞吐和粗粒度显存占用是否变化。

因此每个 variant 都会输出：

- 原始回答
- 按任务规则打分后的逐条结果
- 分类汇总
- 整体质量分数
- 基本性能指标

## 当前任务覆盖

当前任务集优先覆盖 `/work` 中要求的四类场景：

- 长上下文问答
- 多轮对话记忆
- 代码生成
- 推理 / 结构化算题

每类任务先使用轻量、可解释、规则化评分，便于后续替换成更复杂的自动评测或人工抽检流程。

## 快速开始

从 `KVFabric/` 根目录开始：

```bash
cd KVFabric

bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/run_quality_suite.sh
```

默认会执行 `plans/qwen3_5_2b_baseline.env`，也就是只跑一个 `vanilla_vllm` 控制组。

如果要改成自己的对比计划：

```bash
bash experiments/paper_reproductions/kvcache_quality_benchmark/scripts/run_quality_suite.sh \
  experiments/paper_reproductions/kvcache_quality_benchmark/plans/qwen3_5_2b_compare_template.env
```

## 运行输出

每次 suite 运行会在 `runs/` 下生成一组目录：

```text
runs/<timestamp>_<suite_name>/
├─ suite_summary.json
├─ suite_summary.md
└─ <variant_name>/
   ├─ config.json
   ├─ env.json
   ├─ tasks.json
   ├─ raw_outputs.jsonl
   ├─ item_scores.jsonl
   ├─ metrics.json
   └─ summary.md
```

## 当前限制

- 当前仓库里还没有真正的 KV 压缩/量化实现，因此默认只提供 `vanilla_vllm` 控制组和 `candidate_template` 模板。
- 当前打分以规则匹配为主，适合“先把流程跑通、先把退化看出来”，不等价于正式 paper artifact 的完整质量评测。
- 当前性能指标以离线推理时延、输出吞吐和粗粒度 CUDA 显存占用估计为主，不替代后续更严格的 benchmark。

## 推荐下一步

- 当你们真正接入某种 KV 压缩或量化实现时，只需要新增一个 `variants/*.env` 配置，并在必要时扩展 `examples/offline_quality_eval.py` 的可调参数。
- 当任务集需要扩展时，优先新增 `configs/*.json` 而不是直接改脚本逻辑。
