# 当前阶段状态与收尾计划

本文档记录 KVFabric 当前从 vLLM baseline 过渡到控制面 prototype 之后的真实状态。早期的 bring-up、预验证和源码阅读已经完成；当前重点是整理 lifecycle prototype、A/B 结果和最终报告。

## 当前状态

项目已经完成以下过渡：

```text
vLLM baseline
  -> prefix caching 预验证
  -> 纯 Python 生命周期策略最小闭环
  -> vLLM overlay 探针和封装
  -> family-protect / shared-aware 策略原型
  -> 长时间对话压测与模板/多轮 workload 验证
```

当前阶段不再只是“准备修改 vLLM”，而是已经有可应用到 vLLM 工作树的 overlay prototype。

## 当前目录职责

- `vllm_baseline/`
  保留 vLLM 环境、服务启动、停止、metrics 读取和模型 profile。

- `vllm_workspace/`
  管理 vLLM Python 控制面的 overlay，包括 lifecycle tracker、metrics probe、family-protect 策略和 patch 工作流。

- `experiments/prebenchmark_validation/`
  承接真实 vLLM serving 下的小到中等规模请求、lifecycle JSONL、Prometheus metrics 和 A/B 对比。

- `experiments/benchmarks/lifecycle_policy/`
  保留纯 Python 合成闭环，用来解释策略思想和指标定义。

- `experiments/langtime_running_test/`
  承接长时间对话、多轮分叉、压力测试和数据集驱动场景。

- `docs/current/`
  维护当前实现状态、迭代日志、3090 复跑交接和最终收尾计划。

## Prefix Caching 当前理解

vLLM prefix caching 主要复用严格 full-block 公共前缀。共享前缀不足一个 full block 时，prefix hit 可能仍为 0；共享系统前缀足够长后，可以观察到明显命中。

KVFabric 当前没有改变 vLLM 的物理复用语义，而是在 prefix cache 已有能力之上做生命周期管理：

- 记录哪些 block 被命中；
- 识别哪些 block 是共享主干；
- 在显存压力下保护长期复用 family；
- 记录误驱逐和重建行为；
- 用 A/B 说明策略收益和开销。

## 当前建议收尾顺序

1. 确认 overlay 能通过静态编译和 shell 脚本语法检查。
2. 复跑 `ordinary_unique_cold`，确认普通无共享场景低开销退化。
3. 复跑 `template_family_revisit`，确认模板 family 单周期回访收益。
4. 复跑 `template_family_revisit_cycles`，确认多周期回访收益。
5. 生成每次 run 的 lifecycle metrics、Prometheus summary 和 `ab_comparison.md`。
6. 如果时间允许，补一组三方对照：prefix off / prefix on + LRU / prefix on + family-protect。
7. 整理最终报告，按“普通场景无害、复用场景受益、当前仍是 Python prototype”解释。

## 推荐保留的代表性命令

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=3 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_27b \
  experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
```

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_27b \
  experiments/prebenchmark_validation/configs/template_family_revisit.json
```

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_27b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

## 当前结论边界

可以说明：

- lifecycle side table 和事件日志已经接入真实 vLLM 控制面；
- `family_protect` 可以在模板化和相似多轮场景中保护共享主干；
- 当前实验显示 rebuilt-from-eviction 下降、prefix-hit tokens 增加，并有小幅请求级收益；
- 普通无共享场景中策略基本不触发。

不应过度说明：

- 不应说所有 workload 都大幅提速；
- 不应说已经实现 chunk 级任意共享；
- 不应说已经实现真实 CoW；
- 不应说当前已经改变底层执行路径。
