# KVFabric 3090 复跑交接说明

本文档给使用 3090ti 复跑和继续优化 KVFabric 使用。重点是：先复现当前 4070 Laptop / qwen3.5-2B 上已经验证的结论，再逐步加大模型、压力和模板化长对话场景。

## 当前结论

当前 4070 Laptop / qwen3.5-2B 结果还没有证明端到端吞吐提升 30%。目前更稳妥的结论是：

- 普通无共享 serving 场景下，KVFabric 基本不掉速；
- 模板化 prompt、相似多轮对话、长对话回访这类 workload 中，KVFabric 有明显 KV 资源管理收益；
- 这些收益主要体现为：
  - `rebuilt-from-eviction` 下降；
  - `prefix-hit tokens` 增加；
  - TTFT / E2E latency 下降；
  - requests/s 有小幅正收益。


## 应用

先把 overlay 应用到实际 vLLM 环境：

```bash
bash vllm_workspace/scripts/apply_to_worktree.sh
```

需要先确认对应模型已经下载、profile 可用、vLLM 服务能正常启动。

## 推荐复跑顺序

### 1. 普通无共享场景 sanity check

目的：验证 KVFabric 在没有长期共享前缀的普通 serving 场景下不会明显掉速。

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=3 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/ordinary_unique_cold.json
```

### 2. 模板 family 单周期回访

目的：验证模板化 prompt / 相似多轮场景下，KVFabric 是否能保护长期复用的模板 family。

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit.json
```

注意：模板/多轮场景建议使用：

```bash
KVFABRIC_PROTECT_MIN_HIT_COUNT=1
```

如果设为 `3`，当前 workload 中 `hit_count=1` 的复用 block 不会被保护，策略效果会被压掉。

### 3. 模板 family 多周期回访

目的：更接近长对话或相似多轮服务场景。每个周期先用冷请求冲刷 KV cache，再回访长期模板 family。

```bash
KVFABRIC_ADMISSION_ANCHOR_BLOCKS=24 \
KVFABRIC_PROTECT_MIN_HIT_COUNT=1 \
bash experiments/prebenchmark_validation/scripts/run_kvfabric_ab_smoke.sh \
  qwen3_5_2b \
  experiments/prebenchmark_validation/configs/template_family_revisit_cycles.json
```

### 4. 生成 A/B 对比报告

每次跑完后，用下面命令生成报告：

```bash
python experiments/prebenchmark_validation/examples/compare_kvfabric_ab.py \
  <run-dir> \
  --candidate family_protect \
  --output <run-dir>/ab_comparison.md
```

其中 `<run-dir>` 是脚本最后输出的路径，例如：

```text
experiments/prebenchmark_validation/runs/2026-xx-xx_xxxxxx_qwen3_5_2b_template_family_revisit_cycles_kvfabric_ab
```

## 4070 参考结果

下面是当前 4070 Laptop / qwen3.5-2B 上的参考结果，3090 复跑时可以先对齐这些趋势。

### 普通无共享场景

- requests/s: `3.2320 -> 3.2224`，变化 `-0.30%`
- prefix-hit tokens: `0 -> 0`
- rebuilt-from-eviction blocks: `0 -> 0`
- ranking events: `0 -> 0`

结论：普通场景基本不掉速。

### 模板 family 单周期

- requests/s: `3.8651 -> 3.9608`，变化 `+2.48%`
- TTFT avg: `0.1342s -> 0.1280s`
- rebuilt-from-eviction blocks: `40 -> 0`
- prefix-hit tokens: `21760 -> 27200`，变化 `+25.0%`

结论：模板化 prompt / 相似多轮场景中，KVFabric 能把 LRU 误驱逐导致的 rebuild 压掉，并带来请求级正收益。

### 模板 family 多周期

- requests/s: `3.3506 -> 3.4288`，变化 `+2.34%`
- TTFT avg: `0.1714s -> 0.1639s`
- rebuilt-from-eviction blocks: `96 -> 0`
- prefix-hit tokens: `30464 -> 43520`，变化 `+42.86%`

结论：多周期场景更接近长对话/多轮回访，资源管理指标改善更明显。

## 3090 上继续优化的方向

1. 尝试更大模型 profile，或者提高 `GPU_MEMORY_UTILIZATION`，但要保留足够 KV pressure 来触发 eviction。
2. 逐步加大 `template_family_revisit_cycles.json`：
   - `family_count`
   - `cold_pressure_requests`
   - `revisit_cycles`
   - `revisit_per_family`
3. 模板/多轮场景优先保持 `KVFABRIC_PROTECT_MIN_HIT_COUNT=1`。
4. 下一步建议做三组对照：
   - prefix caching off；
   - vLLM prefix caching on + LRU；
   - KVFabric `family_protect`。
5. 如果端到端吞吐提升仍然较小，优先减少观测开销：
   - performance run 只保留聚合 counter；
   - debug run 再写完整 JSONL lifecycle event。
6. 如果 3090 能跑更大模型，优先复跑模板 family 多周期场景，而不是重复所有早期 hot/cold 调参实验。
