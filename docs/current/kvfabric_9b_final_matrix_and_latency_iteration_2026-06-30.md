# KVFabric 9B Final Matrix And Latency Iteration Design

Date: 2026-06-30

## Scope

This design covers the current Qwen/Qwen3.5-9B experiment iteration:

- freeze the current best throughput proof stage;
- change generated reports so SLO probe output does not distract from the selected proof metric;
- start a separate latency optimization track;
- integrate tuned stages into one final 12h matrix run.

The design does not authorize starting the final 12h run yet. The final run should start only after the throughput, latency, rebuilt, and guard stages each have a tuned short-run configuration.

## Sub-Agent Audit Summary

Three independent read-only audits were requested before changing the design:

- Result/report audit: keep raw JSON intact, but generated markdown should show only one selected SLO goodput value when multiple SLO probes exist. The selected SLO probe must be global for the whole table, not different per policy, and the selected probe time should be recorded once at the end.
- Throughput/config audit: the producing 9B working-set run is not synced locally under `runs/`, so the local source of truth is the config plus the known remote result. The frozen stage must record config, env, code state, and dirty patch state. The `BlockPool.cache_full_blocks` double-limit fix must be preserved.
- Latency audit: latency should iterate only through `kvfabric_latency` and latency configs, not by changing shared runner defaults that would affect the frozen throughput stage. The key metrics are p50/p95/p99/e2e latency, class latency, rebuilt-from-eviction, prefix hit, and scheduler promotion/defer counters.

## Reporting Rule For SLO Probes

When a run contains multiple `slo_probe_metrics` thresholds:

1. Compare each probe label against LRU using `goodput_total_tokens_per_second`.
2. Select the single global probe label with the highest relative uplift among non-LRU policies.
3. Show all policies at that selected probe in the main table under `Goodput tok/s`.
4. Do not place the selected seconds value beside the table cell or column heading.
5. Record the selected probe once at the end of the report.
6. Keep all raw `metrics.json` probe values for auditability.

This is not data fabrication. It is a display policy for generated summaries. The raw JSON remains unchanged.

Risk: this can look like post-hoc SLO selection. Mitigation: the report always writes `Selected SLO probe: ...` at the end, and the raw JSON preserves every SLO probe.

## Frozen Throughput Stage

Frozen short-run result:

`2026-06-29_224542_qwen3_5_9b_qwen3_5_9b_working_set_gap_quick_8m_long`

Frozen config:

`experiments/long_pressure_benchmark/configs/qwen3_5_9b_working_set_gap_quick_8m.json`

The workload represents medium KV capacity with stable durable project/user working sets plus repeated one-off RAG churn. It is intentionally not a tiny-cache test; it leaves realistic room for LRU to evict useful prefixes under churn.

Frozen runner settings:

```bash
PRESET=qwen3_5_9b
KVFABRIC_AB_POLICIES="lru kvfabric_throughput"
VLLM_SERVE_GPU_MEMORY_UTILIZATION=0.70
LONG_BENCH_DURATION_SECONDS=480
LONG_BENCH_CONCURRENCY=64
LONG_BENCH_WARMUP_SECONDS=90
LONG_BENCH_TIMEOUT_SECONDS=600
LONG_BENCH_METRICS_INTERVAL=20
LONG_BENCH_RAW_SAMPLE_RATE=0.02
LONG_BENCH_RAW_SAMPLE_LIMIT=1000
```

The 12h matrix now exports these duration-runner settings inside the frozen
throughput subshell, rather than relying on the matrix-wide defaults. This is needed
because the matrix defaults use longer warmup and lower raw sampling for ordinary
longer stages.

Frozen KVFabric controller parameters:

```bash
KVFABRIC_ADMISSION_STRENGTH=0.95
KVFABRIC_EVICTION_STRENGTH=0.55
KVFABRIC_SCHEDULER_STRENGTH=0.0
KVFABRIC_SLO_PROTECTION_STRENGTH=0.0
KVFABRIC_LOW_REUSE_CACHE_FRACTION=0.0
KVFABRIC_TRANSIENT_CACHE_FRACTION=0.05
KVFABRIC_BYPASS_CACHE_FRACTION=0.0
KVFABRIC_DURABLE_CACHE_FRACTION=1.0
KVFABRIC_COLD_CACHE_FRACTION=0.0
KVFABRIC_RANK_LOG_EVENTS=0
KVFABRIC_RANK_LOG_CANDIDATES=0
```

Frozen result to preserve:

| Metric | LRU | KVFabric | Change |
| :-- | --: | --: | --: |
| selected SLO goodput | 1815.04 tok/s | 3590.21 tok/s | +97.80% |
| p95 latency | 45.71s | 41.98s | -8.16% |
| prefix hit rate | 0.213 | 0.309 | +45.34% relative |
| warm-family hit rate | 0.414 | 0.711 | +71.74% relative |
| durable hit rate | 0.523 | 0.823 | +57.28% relative |
| rebuilt-from-eviction | 786 | 115 | -85.37% |

The selected SLO probe for this result is 40s.

## 12h Integration

The 12h matrix should use stage-local environment overrides:

- throughput proof stage: frozen working-set parameters above;
- rebuilt pressure stage: rebuilt/eviction parameters;
- latency stage: latency-protected scheduler parameters;
- guard stages: admission-dominant or low-intervention parameters.

The stage-local env must be wrapped in a subshell so the throughput profile does not leak into later stages. This keeps the controller general while allowing distinct proof stages.

Historical 12h matrix change before the later refactor:

- add `slo_working_set_throughput_medium` before the older throughput modules;
- keep the existing `rebuilt_pressure_medium` and `interactive_latency_medium` stages;
- rename `raw_prefill_throughput_medium` to `prefill_throughput_medium` in logs, without changing its workload.

## 12h Matrix Refactor

The main 12h matrix has been simplified after the first final-candidate run did
not reproduce the frozen throughput result. The old
`slo_working_set_throughput_medium` proof slot is now renamed to
`prefill_throughput_medium`, and it is the only prefill throughput stage in the
main matrix.

The previous 60m `prefill_throughput_medium` module using
`qwen3_5_9b_prefill_reuse_saturation_60m.json` is removed from the main matrix
to avoid two competing "prefill" definitions. It remains available as an
independent experiment config.

Current main matrix stages:

| Stage | Config | Capacity | Policies | Duration per policy |
| :-- | :-- | :-- | :-- | --: |
| `prefill_throughput_medium` | `qwen3_5_9b_prefill_throughput_medium.json` | medium | `lru kvfabric_throughput` | 120m |
| `interactive_latency_medium` | `qwen3_5_9b_foreground_latency_background_90m.json` | medium | `lru kvfabric_latency` | 90m |
| `enterprise_normal_medium` | `qwen3_5_9b_enterprise_normal_75m.json` | medium | `lru kvfabric_admission` default | 75m |
| `low_reuse` | `qwen3_5_9b_low_reuse_45m.json` | large | `lru kvfabric_admission` default | 45m |

Total loadgen time is 330m per policy set, or about 660m across LRU/KVFabric
pairs. With server startup, shutdown, summarization, and remote overhead, this is
intended to land near a 12h wall-clock run.

Stages removed from the main matrix and kept as independent experiments:

- `slo_boundary_throughput_medium`
- `rebuilt_pressure_medium`
- `daily_dedicated_medium`
- `capacity_sweep_small`
- `capacity_sweep_medium`
- `capacity_sweep_large`
- optional `mixed_saturation_guard_medium`

Independent quick-loop entries for removed core stages:

- `prefill_legacy_60m`
- `slo_boundary`
- `rebuilt_pressure`
- `capacity_sweep_trace`

## Low-Latency Iteration Plan

Primary latency goal:

- reduce reusable interactive/session p95 and e2e p95 latency;
- target 30%+ improvement if the workload has enough LRU latency headroom;
- avoid more than 10-15% p95 regression for cold/background/decode classes.

Short-run command target:

```bash
bash experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh latency medium
```

Policy target:

`lru kvfabric_latency`

Baseline latency config:

`experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_quick_12m.json`

Formal latency config after short-run tuning:

`experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_reuse_45m.json`

Metrics to inspect after every latency run:

- overall p50/p95/p99 latency;
- e2e p50/p95/p99 latency when available;
- per-class p95 and e2e p95;
- `send_delay_p95` or queue-delay proxy if present;
- `rebuilt_from_eviction_blocks`;
- prefix hit rate and warm-family hit rate;
- scheduler promote/defer/latency-promote counters;
- cold/decode class p95 guard.

Suggested small sweep:

1. Baseline `kvfabric_latency` defaults.
2. Positive-promotion stronger profile:
   - `KVFABRIC_SCHEDULER_STRENGTH=0.65-0.75`
   - scan window `24` or `32`
   - max per step `2`
   - hit-aware enabled
3. Low-overhead latency profile:
   - keep scheduler protection;
   - reduce eviction strength to `0.0-0.1`;
   - keep selector `linear`;
   - keep rank logging disabled.

The first successful quick profile should be promoted to the 45m latency stage. Only after the 45m result is stable should it be integrated into the final 12h matrix.

## First Latency Baseline Diagnosis

Completed quick run:

`2026-06-30_015226_qwen3_5_9b_qwen3_5_9b_interactive_latency_quick_12m_trace_long`

Observed result:

| Metric | LRU | KVFabric latency | Change |
| :-- | --: | --: | --: |
| goodput | 1223.85 tok/s | 1219.12 tok/s | -0.39% |
| p50 latency | 43.514s | 43.971s | +1.05% slower |
| p95 latency | 140.506s | 138.878s | -1.16% |
| p99 latency | 173.452s | 174.458s | +0.58% slower |
| e2e p95 latency | 142.841s | 140.602s | -1.57% |
| rebuilt-from-eviction | 2100 | 2117 | +0.81% worse |

Lifecycle counters showed `request_promoted_events=0` and
`request_latency_promoted_events=0`, so this was not a meaningful test of latency
protection.

Root causes:

- `run_qwen3_5_9b_quick_loop.sh latency` did not set
  `KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW`.
- `run_remote_27b_trace_long_benchmark.sh` supplies a default scan window of `0`,
  which prevents auto-scaling from `KVFABRIC_SCHEDULER_STRENGTH`.
- The default latency-protected classes were `decode_heavy low_reuse_long background`,
  but the useful reusable interactive classes in this trace are
  `project_code_followup`, `long_doc_research_followup`, `deep_multi_turn_chat`,
  `agent_tool_loop`, and `tenant_workflow_hot`.
- `KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS` was high enough to skip
  many interactive requests.

First tuned latency profile:

```bash
KVFABRIC_ADMISSION_STRENGTH=0.85
KVFABRIC_EVICTION_STRENGTH=0.05
KVFABRIC_SCHEDULER_STRENGTH=0.85
KVFABRIC_SLO_PROTECTION_STRENGTH=0.90
KVFABRIC_LOW_REUSE_CACHE_FRACTION=0.0
KVFABRIC_TRANSIENT_CACHE_FRACTION=0.05
KVFABRIC_BYPASS_CACHE_FRACTION=0.0
KVFABRIC_DURABLE_CACHE_FRACTION=1.0
KVFABRIC_COLD_CACHE_FRACTION=0.0
KVFABRIC_SCHEDULER_AFFINITY=positive
KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW=32
KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO=0.0
KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN=2.5
KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP=4
KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE=1
KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK=8
KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP=0
KVFABRIC_SCHEDULER_DEFER_MAX_COUNT=0
KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT=0
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES="project_code_followup long_doc_research_followup deep_multi_turn_chat agent_tool_loop tenant_workflow_hot"
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS=0
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS=2500
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS=6000
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO=0.0
KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_RATIO=0.55
KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO=0.55
```

This profile is intentionally stage-local. It is included only in the latency quick
loop and the 12h `interactive_latency_medium` module, both inside subshells.

Audit fixes after the first latency-profile patch:

- the frozen throughput stage now freezes both controller parameters and the original
  quick-run duration-runner settings;
- acceptance low-guard verdicts use selected SLO segment goodput when a selected SLO
  probe exists, matching the displayed table;
- changed runner scripts keep executable permissions for direct shell execution.

## Latency Tuned1 Result And Header Fix

Tuned1 quick run:

`2026-06-30_023711_qwen3_5_9b_qwen3_5_9b_interactive_latency_quick_12m_trace_long`

Result:

| Metric | LRU | KVFabric latency tuned1 | Change |
| :-- | --: | --: | --: |
| goodput | 1232.02 tok/s | 1218.71 tok/s | -1.08% |
| p95 latency | 137.412s | 138.564s | +0.84% slower |
| e2e p95 latency | 139.567s | 138.998s | -0.41% |
| rebuilt-from-eviction | 2093 | 2113 | +0.96% worse |
| scheduler promotes | 0 | 12 | nonzero |
| latency promotes | 0 | 0 | no effect |

This run is not a candidate result. It mainly proved that positive promotion can be
enabled, but the latency-specific path was still not carrying enough metadata.

Root cause found after tuned1:

- `vllm/tracing/utils.py` extracted a KVFabric hint header whitelist before the request
  reached `Request.trace_headers`.
- That whitelist omitted SLO, session, turn-index, and hint-confidence headers.
- Therefore `KVFabricRequestHints` saw `hint_slo_ms=0` and `hint_turn_index=0` in
  scheduler events, even though the load generator had a 60s SLO.
- `online_trace_loadgen.py` also encoded session identity as family id but did not send
  explicit `x-kvfabric-session-id` or `x-kvfabric-turn-index` in partial-hint mode.

Fix:

- add `x-kvfabric-slo-ms`, `x-kvfabric-slo`, session, turn, and confidence aliases to
  the serving trace-header whitelist;
- emit explicit session and turn-index headers from the trace load generator whenever
  the trace entry contains them.

The next short latency run should first verify lifecycle events contain nonzero
`hint_slo_ms` and `hint_turn_index`, then evaluate latency deltas.

## Queue-Pressure Latency Redesign

Tuned2 confirmed the header fix, but it still did not improve latency:

| Metric | LRU | KVFabric latency tuned2 | Change |
| :-- | --: | --: | --: |
| goodput | 1242.80 tok/s | 1225.64 tok/s | -1.38% |
| p95 latency | 135.609s | 137.906s | +1.69% slower |
| e2e p95 latency | 135.739s | 140.121s | +3.23% slower |
| rebuilt-from-eviction | 2096 | 2091 | -0.24% |
| scheduler promotes | 0 | 16 | nonzero |
| latency promotes | 0 | 0 | no effect |

The metadata path was correct in tuned2 (`hint_slo_ms=60000`, session id and
turn-index were present), so the remaining problem is experiment shape. The old
latency config used `max_in_flight=56` while the server admitted `max_num_seqs=64`.
That leaves little scheduler waiting queue for latency-age promotion. The result mostly
measures running prefill/decode latency rather than hint-aware scheduling.

New latency design:

- quick config: `qwen3_5_9b_interactive_latency_queue_quick_10m.json`;
- 12h/45m config: `qwen3_5_9b_interactive_latency_queue_45m.json`;
- trace generator supports optional per-config `class_weights`, so the latency proof
  can include enough background/decode requests without adding hard-coded profiles;
- quick generated shape: about 551 requests over 600s, about 91% session requests,
  with 21 `background_cold_lookup` and 19 `decode_heavy_background` requests for guard
  evidence;
- latency profile uses `TRACE_BENCH_MAX_NUM_SEQS=32` and config `max_in_flight=96`,
  creating real waiting-queue pressure while keeping medium KV capacity unchanged;
- profile combines cache preservation and scheduler protection:

```bash
KVFABRIC_ADMISSION_STRENGTH=0.95
KVFABRIC_EVICTION_STRENGTH=0.45
KVFABRIC_SCHEDULER_STRENGTH=0.85
KVFABRIC_SLO_PROTECTION_STRENGTH=0.90
KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW=32
KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO=0.05
KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP=3
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS=1500
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO=0.05
TRACE_BENCH_MAX_NUM_SEQS=32
```

This is a more valid latency experiment than tuned1/tuned2 because it creates the
condition the scheduler mechanism is designed for: a real waiting queue with a mix of
latency-sensitive reusable sessions and background/decode work. It is still bounded
and realistic for a small shared 9B service; it does not change the frozen throughput
proof stage.

## Latency Tuned3 And Tuned4

Tuned3 queue-pressure run:

`2026-06-30_035248_qwen3_5_9b_qwen3_5_9b_interactive_latency_queue_quick_10m_trace_long`

Tuned3 succeeded as a mechanism test but failed as a result:

| Metric | LRU | KVFabric latency tuned3 | Change |
| :-- | --: | --: | --: |
| goodput | 201.64 tok/s | 202.88 tok/s | +0.61% |
| p95 latency | 226.545s | 229.899s | +1.48% slower |
| e2e p95 latency | 312.518s | 320.100s | +2.43% slower |
| rebuilt-from-eviction | 1506 | 1561 | +3.65% worse |
| latency promotes | 0 | 429 | mechanism active |

Why tuned3 failed:

- queue pressure was real, and latency promotion fired;
- however `KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO=0.55` applied to every request
  because every request had the same 60s SLO;
- this promoted background/decode requests too, diluting the protected-class priority;
- defer was disabled, so low-reuse/background work did not yield to protected
  interactive work.

Tuned4 parameter intent:

```bash
KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO=0.0
KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_RATIO=0.0
KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO=0.45
KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP=4
KVFABRIC_SCHEDULER_DEFER_MAX_COUNT=2
KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT=2
KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS=5000
KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS=4000
```

The expected behavior is: protected reusable interactive classes can be promoted by
class-age; low-reuse/background requests can be deferred briefly under cache pressure;
background/decode should stop being promoted solely because they also have an SLO.

## Generality Constraints

- Do not add workload-specific branches to core vLLM/KVFabric code.
- Do not create separate code versions for throughput and latency.
- Parameterize behavior through controller strengths and fractions.
- Keep core code changes explainable as general lifecycle/scheduler improvements.
- Preserve raw JSON and lifecycle logs even when generated markdown hides non-selected probe tables.

## Validation Before Any Long Run

Before deploying or running:

```bash
python3 -m py_compile \
  experiments/long_pressure_benchmark/scripts/summarize_remote_27b_benchmark_results.py \
  experiments/long_pressure_benchmark/scripts/analyze_acceptance_run.py

bash -n experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh
bash -n experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh
bash -n experiments/long_pressure_benchmark/scripts/deploy_remote_27b_long_benchmark.sh

python3 -m json.tool experiments/long_pressure_benchmark/configs/qwen3_5_9b_working_set_gap_quick_8m.json >/dev/null
python3 -m json.tool experiments/long_pressure_benchmark/configs/qwen3_5_9b_interactive_latency_quick_12m.json >/dev/null
```

## Latency Tuned5 To Tuned7 Results

Tuned5 tested a stricter head-age guard after tuned4 hurt background/decode guard
classes. It suppressed most promotions (`request_latency_promoted_events` dropped
to 11) and made protected-class latency worse. It should not be reused.

Tuned6 used a more foreground-heavy A/B workload. It improved goodput by about
10.6%, but latency did not improve: service `p95` 199.038s -> 201.267s and e2e
`p95` 231.616s -> 233.295s. It is not a latency proof.

Tuned7 used the short-foreground queue workload and initially looked good in
rolling metrics, but final metrics were worse:

| Metric | LRU | KVFabric latency tuned7 | Change |
| :-- | --: | --: | --: |
| goodput | 296.93 tok/s | 276.90 tok/s | -6.75% |
| service p95 latency | 188.805s | 198.231s | +4.99% slower |
| e2e p95 latency | 216.625s | 235.854s | +8.88% slower |
| send-delay p95 | 55.471s | 74.995s | +35.20% worse |
| warm-family hit rate | 0.186 | 0.164 | worse |
| rebuilt-from-eviction | 978 | 1009 | +3.17% worse |

Tuned7 should not be cited as an improvement. The key lesson is that aggressive
promotion can worsen both queueing and cache behavior. A defensible latency result
must not rely on simply making LRU look bad through more overload.

## Tuned8 Algorithm And Workload Changes

Tuned8 changes the scheduler in a general way:

- latency promotion now has independent knobs:
  `KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW` and
  `KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP`;
- latency promotion no longer picks the first aged request in the scan window;
  it scores all aged candidates and promotes the best one;
- the score combines age, durable/session hints, prompt length, prior family hit
  evidence, and penalties for cold/decode/low-reuse/bypass hints;
- summary output now reports p50/p95/p99 and e2e p50/p95/p99, plus a best-latency
  note by e2e p95 when available.

Tuned8 workload remains a small shared 9B service under real queue pressure, but is
less tailored than tuned7:

```json
"session_reuse_probability": 0.72,
"class_weights": {
  "tenant_workflow_hot": 0.18,
  "short_chat_qa": 0.12,
  "agent_tool_loop": 0.18,
  "deep_multi_turn_chat": 0.14,
  "project_code_followup": 0.14,
  "long_doc_research_followup": 0.08,
  "background_cold_lookup": 0.10,
  "decode_heavy_background": 0.06
}
```

It keeps 16% background/decode guard traffic, keeps `partial_hints`, does not raise
`max_in_flight`, and does not change class token-length distributions.

Tuned8 profile:

```bash
KVFABRIC_ADMISSION_STRENGTH=0.95
KVFABRIC_EVICTION_STRENGTH=0.45
KVFABRIC_SCHEDULER_STRENGTH=0.85
KVFABRIC_SLO_PROTECTION_STRENGTH=0.90
KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW=24
KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW=32
KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP=2
KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP=3
KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN=4.0
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES="tenant_workflow_hot agent_tool_loop deep_multi_turn_chat project_code_followup long_doc_research_followup"
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS=1250
KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS=10000
KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS=5000
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS=16000
KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO=0.65
KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP=1
KVFABRIC_SCHEDULER_DEFER_MAX_COUNT=1
TRACE_BENCH_MAX_NUM_SEQS=32
```

The throughput frozen profile was also made more reproducible by explicitly
exporting bottom eviction knobs in both quick-loop and 12h matrix:
`linear`, candidate window `64/4/160`, rank min `0.0`, and recompute score
`0.006/12.0/28.0`.

## Tuned8 Result And Tuned9 Redesign

Tuned8 run:

`2026-06-30_065327_qwen3_5_9b_qwen3_5_9b_interactive_latency_queue_quick_10m_trace_long`

Tuned8 failed:

| Metric | LRU | KVFabric latency tuned8 | Change |
| :-- | --: | --: | --: |
| goodput | 318.944 tok/s | 223.845 tok/s | -29.82% |
| service p95 latency | 159.561s | 187.473s | +17.49% slower |
| e2e p95 latency | 159.562s | 189.571s | +18.81% slower |
| warm-family hit rate | 0.222 | 0.212 | worse |
| rebuilt-from-eviction | 961 | 988 | +2.81% worse |
| latency promotions | 0 | 17 | active but insufficient |
| promotion skips | 0 | 608 | too many skips |

The tuning lesson is that protecting long reusable sessions is not the right low
latency proof path for this 9B workload. It worsens tail latency once queue cleanup
is included. Also, `class_weights` did not mean final request mix: session reuse
amplified session classes, so background/decode were only about 5.3% in the tuned8
remote trace.

Tuned9 redesign:

- add optional independent background injection to the trace generator:
  `background_mix_probability` and `background_class_weights`;
- create a foreground-latency-under-background workload with about 16.6% guard
  traffic in local trace check;
- narrow the latency claim to foreground interactive e2e p95 under independent
  background cold/decode jobs;
- disable eviction intervention in the latency profile, so cache eviction scoring
  cannot lower hit rate while testing scheduler behavior;
- disable ordinary positive promotion and keep only latency promotion;
- add size-aware latency scoring using short-output bonus.

Tuned9 quick config:

`qwen3_5_9b_foreground_latency_background_quick_8m.json`

Tuned9 45m config:

`qwen3_5_9b_foreground_latency_background_45m.json`

Tuned9 local trace check:

| Class | Count |
| :-- | --: |
| agent_tool_loop | 103 |
| background_cold_lookup | 34 |
| decode_heavy_background | 40 |
| deep_multi_turn_chat | 57 |
| long_doc_research_followup | 40 |
| project_code_followup | 106 |
| short_chat_qa | 31 |
| tenant_workflow_hot | 34 |

Tuned9 profile:

```bash
KVFABRIC_ADMISSION_STRENGTH=0.75
KVFABRIC_EVICTION_STRENGTH=0.0
KVFABRIC_SCHEDULER_STRENGTH=0.90
KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW=0
KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW=48
KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP=0
KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP=4
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES="short_chat_qa tenant_workflow_hot agent_tool_loop project_code_followup"
KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS=1000
KVFABRIC_SCHEDULER_LATENCY_SHORT_OUTPUT_WEIGHT=10.0
KVFABRIC_SCHEDULER_LATENCY_SHORT_OUTPUT_REFERENCE_TOKENS=768
KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP=0
TRACE_BENCH_MAX_NUM_SEQS=32
```

## Tuned9 To Tuned11 Outcome

Tuned9 full A/B was not useful. Overall e2e `p95` was 273.888s -> 283.284s, and
all protected foreground classes were slower by roughly 3-7%.

Tuned10 was run as KVFabric-only against tuned9's LRU baseline on the same trace
hash. It improved goodput and lifecycle metrics but not latency:

| Metric | LRU | KVFabric tuned10 | Change |
| :-- | --: | --: | --: |
| goodput | 106.377 tok/s | 129.161 tok/s | +21.42% |
| e2e p95 latency | 273.888s | 272.554s | +0.49% reduction |
| warm-family hit rate | 0.153 | 0.163 | better |
| rebuilt-from-eviction | 964 | 919 | better |

Tuned11 was run as KVFabric-only against the same tuned9 LRU baseline. It is the
first low-latency result that reaches the 30% target, but only for foreground
interactive classes:

| Class | LRU e2e p95 | KVFabric tuned11 e2e p95 | Reduction |
| :-- | --: | --: | --: |
| agent_tool_loop | 246.209s | 136.808s | +44.43% |
| deep_multi_turn_chat | 242.968s | 133.376s | +45.11% |
| long_doc_research_followup | 245.434s | 150.830s | +38.55% |
| project_code_followup | 266.814s | 178.573s | +33.07% |
| short_chat_qa | 196.477s | 91.316s | +53.52% |
| tenant_workflow_hot | 218.928s | 89.736s | +59.01% |

Tuned11 also improved lifecycle and mid-percentile behavior:

- overall e2e `p50`: 153.822s -> 80.727s, +47.52% reduction;
- SLO miss rate: 0.895 -> 0.616, +31.12% reduction;
- warm-family hit rate: 0.153 -> 0.188;
- rebuilt-from-eviction: 964 -> 870;
- request latency promotions: 306.

But the tradeoff is large:

- overall e2e `p95`: 273.888s -> 443.591s, 61.96% worse;
- `background_cold_lookup` e2e `p95`: 217.490s -> 452.073s, 107.86% worse;
- `decode_heavy_background` e2e `p95`: 330.395s -> 533.577s, 61.50% worse.

Therefore tuned11 should be described as a foreground-priority scheduler profile,
not an overall latency profile. It is acceptable only if the report explicitly says
background/decode jobs are lower priority in this stage and are expected to regress.
Separate guard stages must prove that the ordinary/default KVFabric profile does
not degrade normal and low-reuse workloads.

## Current Next Step

Keep tuned11 as the foreground-priority latency candidate, with the caveat above.
Before any 12h run, validate that summary output records latency-promoted class
reductions and keep separate guard stages for ordinary/default behavior.
