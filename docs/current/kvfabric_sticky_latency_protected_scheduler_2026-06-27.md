# Sticky Conversation 延迟保护调度改动

日期：2026-06-27

## 背景

上一轮 Sticky Conversation 4h 跑完后，整体实验已经没有错误，age guard 也解决了低复用冷请求被长期饿死的问题。新的主要问题集中在 `decode_heavy_noise`：

- LRU p95 约 252s
- `shared_aware` p95 约 358s
- `family_protect` p95 约 354s

这说明当前复用优先调度在长输出、低复用请求上有副作用。它们几乎不能从 prefix reuse 中获益，却会在 waiting 队列里给高复用会话让路。对 Sticky Conversation 这类验收场景来说，长对话和长输出噪声都应该有稳定尾延迟，不能只证明 cache 命中保护有效。

## 设计目标

这次改动只解决 Sticky 类负载的延迟问题，不改变吞吐率证明实验的默认行为。

目标如下：

- 长输出低复用请求不再被 KVFabric defer。
- 当这类请求在 waiting 队列里等待超过阈值后，可以被提到队头。
- 当这类请求已经在队头等待超过阈值后，后面的高复用请求不能继续 promotion 插队。
- 默认配置关闭，只有 Sticky launcher 显式打开，避免影响 saturation throughput 实验的结果。
- 生命周期日志记录新的触发证据，后续可以判断策略是否真的生效。

## 改动内容

新增环境变量：

- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES`
- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS`
- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS`
- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS`
- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO`

默认情况下 `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES` 为空，因此逻辑不启用。

Sticky 4h/12h launcher 使用：

```bash
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES="decode low_reuse_long"
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS=512
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS=8000
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS=20000
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO=0.35
```

这会覆盖 `decode_heavy_noise`，也覆盖低复用且长输出的请求，但不会覆盖普通短冷请求。

## 调度逻辑

waiting 队列调度现在多了一步：

1. 如果启用了 latency protection，先扫描窗口内的候选请求。
2. 如果某个候选请求满足“低复用/指定 class + 长输出 + 等待时间超过阈值”，则把它提到队头。
3. 如果没有触发 latency promotion，再走原来的 positive promotion 逻辑。
4. 在 positive promotion 时，如果队头请求已经触发 latency head guard，则拒绝后面的高复用请求插队。
5. 在 defer 判断时，latency protected 请求直接跳过 defer，并记录 skip reason。

这样可以保留 shared-aware/family-protect 对热会话的 cache 保护，同时避免长输出低复用请求被长期推后。

## 与吞吐率证明实验的关系

saturation throughput 实验不设置这些变量，所以不会启用该逻辑。Enterprise Mixed launcher 只做变量透传，默认仍为空。

如果后续希望在 saturation 实验也打开这套逻辑，需要单独跑 A/B，因为它可能改善尾延迟，但也可能减少高复用请求的连续 batching，从而影响吞吐证明。

## 新增观测字段

`kvfabric_lifecycle_metrics.json` 新增：

- `request_latency_promoted_events`
- `scheduler_latency_promote_hint_classes`
- `scheduler_latency_promote_reasons`
- `scheduler_latency_promote_avg_age_ms`
- `scheduler_latency_promote_max_age_ms`

远程 summary 和 acceptance analysis 表格也新增 `Latency promotes` 列。

## 预期结果

下一轮 Sticky 4h 重点看：

- `decode_heavy_noise` avg/p95 是否明显下降。
- `cold_rag_noise` 是否继续保持无 900s 级尾延迟。
- `deep_multi_turn_chat` 和 `long_doc_followup_qa` 是否没有明显退化。
- `request_latency_promoted_events` 是否主要来自 `decode_heavy_noise`。
- `request_defer_skipped_events` 中是否出现 `latency_protected_defer_bypass`。
- `shared_aware` 的 rebuilt-from-eviction 降幅是否仍明显。

如果 decode-heavy 延迟下降，但热对话延迟明显变差，需要把 `PROMOTE_AGE_MS` 调高或把 `low_reuse_long` 从 protected classes 中去掉，只保留 `decode`。
