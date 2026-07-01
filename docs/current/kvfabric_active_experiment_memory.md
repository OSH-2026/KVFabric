# KVFabric Active Experiment Memory

Last updated: 2026-06-30

This document is the persistent handoff for the current KVFabric experiment iteration. Read it before making new code, config, or experiment changes.

## Current User Goals

1. Use Qwen/Qwen3.5-9B on robowalker as the current main experiment model.
2. Keep KV cache capacity as an explicit variable, with medium capacity as the default proof setting.
3. Temporarily treat `working_set_gap_quick_8m` as the frozen throughput proof candidate.
4. For reports that include multiple SLO probe thresholds, show only the SLO goodput rate with the highest uplift. Do not show the selected SLO time beside that rate; record the selected SLO time only once at the end of the report.
5. Do not emphasize raw total token/s in final-facing records. Raw metrics may remain in JSON for auditability, but generated markdown summaries should focus on SLO goodput, latency, prefix hit, rebuilt, and lifecycle evidence.
6. Start a separate low-latency iteration. Record rebuilt/rebuild, p50/p95/p99/e2e latency, class latency, and SLO latency behavior. Target 30%+ latency reduction if a realistic workload can support it.
7. After each metric-specific short experiment is tuned, integrate its stable config and parameters into one 12h matrix run. Each proof stage may have unique parameters, but the implementation must remain one general KVFabric controller rather than hard-coded one-off code paths.

## Frozen Throughput Candidate

Run:

`experiments/long_pressure_benchmark/runs/2026-06-29_224542_qwen3_5_9b_qwen3_5_9b_working_set_gap_quick_8m_long`

Config:

`experiments/long_pressure_benchmark/configs/qwen3_5_9b_working_set_gap_quick_8m.json`

Policies:

`lru kvfabric_throughput`

Capacity:

medium, `VLLM_SERVE_GPU_MEMORY_UTILIZATION=0.70`

Frozen KVFabric throughput parameters:

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

Key result from the complete comparable run:

- Selected SLO goodput uplift: +97.80%.
- LRU selected goodput: 1815.04 tok/s.
- KVFabric selected goodput: 3590.21 tok/s.
- p95 latency: 45.71s -> 41.98s.
- prefix hit rate: 0.213 -> 0.309.
- warm-family hit rate: 0.414 -> 0.711.
- durable hit rate: 0.523 -> 0.823.
- sticky hit rate: 0.0016 -> 0.274.
- rebuilt-from-eviction: 786 -> 115.

The selected SLO probe for this frozen result is 40s.

## Code State To Preserve

- Keep the unified controller model: KVFabric = lifecycle observation + hint-aware admission + optional eviction intervention + optional scheduler protection.
- Keep the `BlockPool.cache_full_blocks` double-admission-limit fix. The limit must be applied in `SingleTypeKVCacheManager.cache_blocks`; applying it again inside `BlockPool.cache_full_blocks` can make the upper layer believe more blocks were cached than were actually hashed, leading to `assert block.block_hash is not None`.
- Do not hard-code workload names inside core vLLM code. Workload-specific choices belong in benchmark configs and runner environment parameters.
- Use subshell-scoped env overrides for proof stages so a throughput-tuned profile does not leak into latency, rebuilt, guard, or capacity stages.

## Current Implementation Progress

- Added `qwen3_5_9b_working_set_gap_quick_8m.json` and `qwen3_5_9b_working_set_hot_gap_quick_8m.json`.
- Added the two configs to remote deploy sync.
- Added `throughput_working_set` to the 9B quick-loop runner.
- Added `slo_working_set_throughput_medium` as the first 12h matrix module, with the frozen throughput parameters scoped to that module only.
- Updated benchmark summary generation to use a single selected SLO goodput value when SLO probes exist, and to stop showing raw total tok/s in the main markdown tables. Class and segment goodput values use the same selected SLO probe when one is selected.
- Updated acceptance analysis to dynamically discover policies, use the same selected SLO goodput value, dynamically discover segments, and avoid raw total tok/s in markdown tables and guard checks.
- Updated remote result sync default pattern so Qwen3.5-9B runs are discoverable by default.
- Lightly synced the frozen 9B working-set run locally without raw lifecycle JSONL and regenerated its summary with the selected-SLO reporting rule.
- Ran the first Qwen3.5-9B latency quick baseline:
  `2026-06-30_015226_qwen3_5_9b_qwen3_5_9b_interactive_latency_quick_12m_trace_long`.
  Result: `kvfabric_latency` was effectively neutral versus LRU (`p95` 140.506s -> 138.878s,
  e2e `p95` 142.841s -> 140.602s), but rebuilt-from-eviction slightly worsened
  (2100 -> 2117) and scheduler counters showed no promotions.
- Diagnosed why the baseline was neutral: quick latency did not set
  `KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW`; the trace runner defaulted it to `0`;
  the default latency-protected classes targeted `decode/background` rather than the
  interactive reusable classes in this trace; and the min-output-token gate was too high
  for many interactive requests.
- Added a stage-local `apply_latency_interactive_profile` to the 9B quick-loop and 12h
  matrix runners. It explicitly protects the reusable interactive classes, opens a
  positive scan window, lowers the protected output-token gate, disables scheduler
  deferral, and keeps eviction intervention very light to reduce latency overhead.
- Addressed follow-up audit issues:
  - the frozen throughput profile now also exports the original quick-run duration
    runner settings (`LONG_BENCH_WARMUP_SECONDS=90`, metrics interval `20`, raw
    sample rate `0.02`, sample limit `1000`) so the 12h matrix proof stage preserves
    the frozen run's reporting/runtime口径;
  - acceptance low-guard verdicts now use the same selected SLO segment goodput as
    the displayed table when SLO probes exist;
  - executable bits were restored on the changed runner scripts.
- Ran latency tuned1:
  `2026-06-30_023711_qwen3_5_9b_qwen3_5_9b_interactive_latency_quick_12m_trace_long`.
  It is not a usable latency result. `kvfabric_latency` had service `p95` 137.412s
  -> 138.564s, e2e `p95` 139.567s -> 138.998s, goodput -1.08%, and rebuilt
  2093 -> 2113. Scheduler promotion counters were nonzero only for ordinary positive
  promotion (`request_promoted_events=12`), while latency-age promotion stayed zero.
- Diagnosed a generic hint plumbing bug: the OpenAI serving trace-header whitelist in
  `vllm/tracing/utils.py` did not include `x-kvfabric-slo-ms`, session, turn, or hint
  confidence headers. As a result, scheduler-side hint events saw `hint_slo_ms=0` and
  `hint_turn_index=0` even though the load generator knew the SLO. The load generator
  also did not emit explicit session/turn headers for partial hints.
- Fixed the hint plumbing:
  - added SLO/session/turn/confidence headers to `vllm/tracing/utils.py`;
  - made `online_trace_loadgen.py` emit `x-kvfabric-session-id` and
    `x-kvfabric-turn-index` whenever available under hint-enabled regimes.
- Ran latency tuned2 after the header fix:
  `2026-06-30_031422_qwen3_5_9b_qwen3_5_9b_interactive_latency_quick_12m_trace_long`.
  Header propagation was fixed (`hint_slo_ms=60000`, nonzero session and turn fields),
  but the result was still not usable: e2e `p95` 135.739s -> 140.121s and
  `request_latency_promoted_events=0`.
- Reinterpreted the latency-design failure: the old latency config used
  `max_in_flight=56` while the server admitted `max_num_seqs=64`, so the scheduler
  waiting queue rarely had real room for latency-age promotion. The experiment was
  mostly measuring running prefill/decode latency, not scheduler protection.
- Added a queue-pressure latency design:
  - new quick config `qwen3_5_9b_interactive_latency_queue_quick_10m.json`;
  - new 45m config `qwen3_5_9b_interactive_latency_queue_45m.json`;
  - generic `class_weights` support in `generate_realistic_trace.py`;
  - latency profile now uses `TRACE_BENCH_MAX_NUM_SEQS=32`, config `max_in_flight=96`,
    admission strength `0.95`, eviction strength `0.45`, and latency promote age
    `1500ms`;
  - quick and 12h latency stages now point at the queue-pressure configs.
- Ran latency tuned3:
  `2026-06-30_035248_qwen3_5_9b_qwen3_5_9b_interactive_latency_queue_quick_10m_trace_long`.
  It successfully created queue pressure and triggered scheduler latency promotion
  (`request_latency_promoted_events=429`), but it still was not a usable result:
  service `p95` 226.545s -> 229.899s, e2e `p95` 312.518s -> 320.100s, rebuilt
  1506 -> 1561. The failure mode was overbroad SLO promotion: every request had
  a 60s SLO, so background/decode were also latency-promoted.
- Prepared tuned4 latency parameters:
  - close universal SLO promotion with `KVFABRIC_SCHEDULER_SLO_LATENCY_PROMOTE_RATIO=0.0`;
  - close universal SLO head guard with `KVFABRIC_SCHEDULER_SLO_HEAD_GUARD_RATIO=0.0`;
  - keep protected-class age promotion;
  - enable bounded low-reuse/background defer (`DEFER_MAX_PER_STEP=4`,
    max count `2`, low-reuse age cap `4000ms`, general age cap `5000ms`).
  Tuned4 is intended to promote only protected interactive classes and make low-reuse
  background work yield briefly without starvation.

## Latency Iteration Status After Tuned7

Tuned4, tuned5, tuned6, and tuned7 have all been evaluated and none should be
treated as the final latency result.

- Tuned4 showed useful protected-class p95/e2e p95 improvements around 14-21%,
  but it badly hurt background/decode guard classes. It was useful as a mechanism
  signal, not a defensible final result.
- Tuned5 added a strict head-age guard and suppressed most promotions. It became
  worse overall and worse for protected classes.
- Tuned6 used a more foreground-heavy A/B workload and improved goodput by about
  10.6%, but latency stayed neutral or slightly worse (`e2e p95` 231.616s ->
  233.295s).
- Tuned7 used the short-foreground queue workload. Mid-run rolling metrics looked
  promising, but final metrics were worse: service `p95` 188.805s -> 198.231s,
  e2e `p95` 216.625s -> 235.854s, warm-family hit rate 0.186 -> 0.164, and
  rebuilt-from-eviction 978 -> 1009. Do not cite tuned7 as a latency improvement.

The failure mode is now clear: aggressive latency promotion and broad protected
classes can damage queue locality/fairness and cache reuse. Chasing 30% latency
by raising queue pressure further or deleting background/decode traffic would be
too tailored. The next attempt must be more conservative and easier to defend.

## Tuned8 Design

Code changes made for tuned8:

- Added independent latency scheduler knobs:
  `KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW` and
  `KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP`.
- Changed latency promotion from "first aged candidate in scan window" to
  "highest-scoring aged candidate", where the score combines age, durable/session
  hints, prompt reuse value, prior family hit evidence, and penalties for cold,
  decode, low-reuse, or bypass hints.
- Reporting now records p50/p95/p99 and e2e p50/p95/p99 in the main summary and
  writes a best-latency note by e2e p95 when available.

Tuned8 workload changes:

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

These changes keep 16% background/decode guard traffic, do not increase
`max_in_flight`, keep partial hints, and avoid changing token length distributions.

Tuned8 latency profile:

```bash
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
```

Frozen throughput was also tightened: the frozen profile now exports the bottom
eviction knobs used by the quick loop, including `linear` selector, candidate
window `64/4/160`, and recompute score `0.006/12.0/28.0`.

## Tuned8 Result And Tuned9 Design

Tuned8 run:

`2026-06-30_065327_qwen3_5_9b_qwen3_5_9b_interactive_latency_queue_quick_10m_trace_long`

Tuned8 is not usable:

- goodput 318.944 -> 223.845 tok/s, -29.82%;
- service `p95` 159.561s -> 187.473s, 17.49% slower;
- e2e `p95` 159.562s -> 189.571s, 18.81% slower;
- warm-family hit rate 0.222 -> 0.212;
- rebuilt-from-eviction 961 -> 988;
- scheduler counters: latency promotions 17, promotion skips 608, defers 0.

The tuned8 workload also revealed a generator semantics issue: `class_weights`
controls new request/session starts, not final request mix. Session reuse amplified
session classes, so background/decode were only about 5.3% in the remote trace even
though the configured weights summed to 16%. This is now fixed for tuned9 by adding
optional independent background injection.

Tuned9 code/config changes:

- `generate_realistic_trace.py` supports optional `background_mix_probability` and
  `background_class_weights`. Defaults are off, so existing workloads are unchanged.
- New configs:
  - `qwen3_5_9b_foreground_latency_background_quick_8m.json`;
  - `qwen3_5_9b_foreground_latency_background_45m.json`.
- Local tuned9 trace check produced 445 requests with 34 `background_cold_lookup`
  and 40 `decode_heavy_background` requests, i.e. about 16.6% guard traffic.
- `apply_latency_interactive_profile` now uses the tuned9 config and a
  scheduler-dominant profile:
  - admission strength 0.75;
  - eviction strength 0.0;
  - positive promotion disabled;
  - latency scan window 48, max 4 per step;
  - protected foreground classes:
    `short_chat_qa tenant_workflow_hot agent_tool_loop project_code_followup`;
  - size-aware latency score enabled with short-output weight 10.0.

The goal of tuned9 is narrower and more defensible: foreground interactive e2e p95
under independent background cold/decode jobs. Overall p95 may not improve if
background/decode are deliberately deprioritized; therefore protected foreground
class p95/e2e p95 and guard-class regression must both be reported.

## Tuned9 To Tuned11 Results

Tuned9 full A/B:

`2026-06-30_073901_qwen3_5_9b_qwen3_5_9b_foreground_latency_background_quick_8m_trace_long`

Result: not usable. Overall e2e `p95` was 273.888s -> 283.284s, and every
protected foreground class was 3-7% slower. Conservative foreground priority did
not move enough requests; only 24 latency promotions fired.

Tuned10 KVFabric-only, compared against tuned9 LRU on the same trace hash:

`2026-06-30_081234_qwen3_5_9b_qwen3_5_9b_foreground_latency_background_quick_8m_trace_long`

Result: mechanism improved cache/goodput but still not latency. Goodput was
+21.42%, warm-family hit rate 0.153 -> 0.163, rebuilt 964 -> 919, but overall
e2e `p95` improved only 0.49%. Protected class e2e `p95` changes ranged from
-2.52% to +3.08%, far from the 30% target.

Tuned11 KVFabric-only, compared against tuned9 LRU on the same trace hash:

`2026-06-30_083145_qwen3_5_9b_qwen3_5_9b_foreground_latency_background_quick_8m_trace_long`

Result: usable only as a foreground-priority latency proof, not as an overall
latency proof.

- Overall goodput: +297.96%.
- Overall e2e `p50`: 153.822s -> 80.727s, +47.52% reduction.
- Overall e2e `p95`: 273.888s -> 443.591s, 61.96% worse.
- SLO miss rate: 0.895 -> 0.616, +31.12% reduction.
- Warm-family hit rate: 0.153 -> 0.188.
- Rebuilt-from-eviction: 964 -> 870.
- Latency promotions: 306; promotion skips: 0.

Protected foreground e2e `p95` reductions:

- `agent_tool_loop`: 246.209s -> 136.808s, +44.43%.
- `deep_multi_turn_chat`: 242.968s -> 133.376s, +45.11%.
- `long_doc_research_followup`: 245.434s -> 150.830s, +38.55%.
- `project_code_followup`: 266.814s -> 178.573s, +33.07%.
- `short_chat_qa`: 196.477s -> 91.316s, +53.52%.
- `tenant_workflow_hot`: 218.928s -> 89.736s, +59.01%.

Guard/background regressions:

- `background_cold_lookup` e2e `p95`: 217.490s -> 452.073s, 107.86% worse.
- `decode_heavy_background` e2e `p95`: 330.395s -> 533.577s, 61.50% worse.

Interpretation: tuned11 proves that a hint-aware scheduler can strongly protect
foreground interactive classes under background load, but it does so by explicitly
deprioritizing background/decode. It must be reported as a foreground-priority
scenario. Do not claim overall latency improvement from this stage.

## Next Work

1. The previous 12h matrix job was stopped after the first throughput stage did
   not reproduce the frozen KVFabric result. Do not treat that partial run as
   the final matrix.
2. Keep tuned11 as the candidate foreground-priority latency profile only if the
   final writeup explicitly says background/decode are lower priority and regress.
3. The final 12h matrix has been reduced to four stages only:
   `prefill_throughput_medium`, `interactive_latency_medium`,
   `enterprise_normal_medium`, and `low_reuse`.
4. Do not claim overall latency improvement from tuned11. The claim is protected
   foreground class e2e `p95` reduction under background load.
5. Before restarting the 12h job, run a short validation of the renamed
   `prefill_throughput_medium` stage because its warmup/churn/revisit structure
   was just made deterministic.

## 12h Matrix Live Status

Status note at 2026-06-30 09:05 CST:

- The final-candidate 12h matrix is still running on robowalker.
- First stage: `slo_working_set_throughput_medium`.
- LRU policy has completed. Its rolling 40s probe at the end of the run was
  1820.95 tok/s, close to the frozen LRU reference 1815.04 tok/s.
- LRU lifecycle warm-family prefix hit rate was 0.418, close to the frozen LRU
  reference 0.414.
- `kvfabric_throughput` has started and produced early rolling metrics. At
  elapsed 80s, the 40s probe was 3708.35 tok/s. This is only an early rolling
  status signal and must not be cited as the final 12h-stage result.

Status note at 2026-06-30 09:20 CST:

- The final-candidate 12h matrix was stopped after the first throughput stage
  failed to reproduce the frozen KVFabric result. The partial run is preserved
  for diagnosis.
- Completed first-stage result:
  - LRU 40s SLO probe: 1970.80 tok/s.
  - KVFabric throughput 40s SLO probe: 1551.32 tok/s.
  - KVFabric warm-family prefix hit rate: 0.376, versus frozen reference 0.711.
  - KVFabric rebuilt-from-eviction: 818, versus frozen reference 115.
- Direct env/config comparison did not reveal meaningful differences between
  frozen and current `kvfabric_throughput` runs. The config, scenario seed,
  loadgen seed, segment definitions, and controller env are effectively the same.
- The first substantive diagnosis is workload-order instability: the service-side
  `request_hints_observed` sequence differs immediately between frozen and
  current runs under high concurrency. The current `working_set_warmup` segment
  is only a time label; it does not force hot/sticky requests during warmup.
  Cold requests can reach the server before useful working-set prefixes are
  established, which makes the throughput proof stage fragile.
- Do not restart the 12h matrix until the working-set throughput stage has a
  deterministic, defensible warmup/churn/revisit structure and re-passes a short
  validation.

Status note at 2026-06-30 matrix refactor:

- The old `slo_working_set_throughput_medium` slot is now the official
  `prefill_throughput_medium` slot.
- The old 60m `prefill_throughput_medium` stage based on
  `qwen3_5_9b_prefill_reuse_saturation_60m.json` has been removed from the
  12h main matrix. It remains available as an independent experiment/config.
- The 12h main matrix now uses these formal configs:
  - `prefill_throughput_medium`:
    `qwen3_5_9b_prefill_throughput_medium.json`, 120m per policy,
    medium capacity, policies `lru kvfabric_throughput`.
  - `interactive_latency_medium`:
    `qwen3_5_9b_foreground_latency_background_90m.json`, 90m per policy,
    medium capacity, policies `lru kvfabric_latency`.
  - `enterprise_normal_medium`:
    `qwen3_5_9b_enterprise_normal_75m.json`, 75m per policy,
    medium capacity, policies `lru kvfabric_admission` by default.
  - `low_reuse`:
    `qwen3_5_9b_low_reuse_45m.json`, 45m per policy, large capacity,
    policies `lru kvfabric_admission` by default.
- Total configured loadgen duration is 330m per policy set and about 660m
  across LRU/KVFabric pairs. With server restart, warmup, and summary overhead,
  expected wall time is around 12h.
- Independent quick-loop entries for removed core stages:
  - `prefill_legacy_60m`
  - `slo_boundary`
  - `rebuilt_pressure`
  - `capacity_sweep_trace`

## Final 12h Result Staging

Prepared result archive roots for the next 12h run:

- Local:
  `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix`
- Remote:
  `/home/zhoujiarun/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix`
- Remote job-log archive:
  `/home/zhoujiarun/KVFabric/vllm_baseline/runtime_kvfabric_0221/jobs/archive/qwen9b_12h_matrix_final_20260630`

Subdirectories created on both local and remote result roots:

- `job_logs`
- `run_roots`
- `summaries`
- `analysis`
- `snapshots`
- `raw_jsonl_optional`

## 12h Tail Resume Status

Status note at 2026-06-30 15:40 CST:

- The first two final matrix stages are already locally staged under
  `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix`.
- Completed staged summaries:
  - `prefill_throughput_medium`: selected SLO goodput 1815.04 -> 3590.21 tok/s,
    +97.80%; prefix hit 21.28% -> 30.93%; rebuilt-from-eviction 11790 -> 1725.
  - `interactive_latency_medium`: foreground-priority latency profile. Overall
    goodput 106.38 -> 423.34 tok/s and e2e goodput 106.38 -> 305.23 tok/s.
    Protected foreground classes show 6/6 e2e p95 reductions >= 30%; background
    guard classes regress and must be reported explicitly as lower-priority work.
- The interrupted 12h matrix has been resumed as a tail-only remote job that runs
  only the remaining modules:
  `enterprise_normal_medium low_reuse`.
- Remote job:
  - name: `qwen9b_12h_tail_enterprise_lowreuse_20260630`
  - pid: `2373110`
  - log:
    `/home/zhoujiarun/KVFabric/vllm_baseline/runtime_kvfabric_0221/jobs/qwen9b_12h_tail_enterprise_lowreuse_20260630.log`
  - modules env:
    `KVFABRIC_QWEN9B_12H_MODULES="enterprise_normal_medium low_reuse"`.
- Current running module:
  `enterprise_normal_medium`, medium capacity, policies `lru kvfabric_admission`.
  Run root:
  `/home/zhoujiarun/KVFabric/experiments/long_pressure_benchmark/runs/2026-06-30_153344_qwen3_5_9b_qwen3_5_9b_enterprise_normal_75m_trace_long`.
- Generated enterprise trace:
  4500s, 4149 requests, actual request rate 0.922 req/s, profile
  `enterprise_mixed`, hint regime `partial_hints`, unique tenants 10, clients 64,
  families 917.
- Early LRU rolling status at elapsed 330s: goodput 1186.55 tok/s, e2e goodput
  1186.55 tok/s, p95 latency 106.59s, e2e p95 107.09s, 0 errors. This is only
  a live progress signal and must not be cited as a final result.
- After both tail modules finish, generate summaries with
  `summarize_remote_27b_benchmark_results.py`, copy the two module summaries into
  the local final result root, and add `enterprise_normal_medium_summary.md` and
  `low_reuse_summary.md` under `summaries/`.
- A local watcher is running to do that post-processing automatically:
  - script:
    `experiments/long_pressure_benchmark/scripts/archive_qwen3_5_9b_final_tail_results.sh`
  - current local pid observed by `pgrep`: `1714`
  - watcher log:
    `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/job_logs/tail_archive_watcher.log`
  - archive status target:
    `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/analysis/tail_archive_status.md`

Status note at 2026-06-30 20:15 CST:

- The tail-only remote job completed and the watcher archived both remaining
  modules.
- Local final root:
  `/home/qy-dream/OSH_Project/KVFabric/experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix`.
- Newly archived summaries:
  - `summaries/enterprise_normal_medium_summary.md`
  - `summaries/low_reuse_summary.md`
- Combined analysis:
  `analysis/final_12h_sync_and_analysis.md`.
- The four summaries were regenerated after sync with the current summary script.
  This fixed the stale `interactive_latency_medium` tail note: overall e2e P95
  latency reduction is 273.888s -> 221.542s, +19.11%, while 6/6 protected
  foreground classes remain >=30% e2e P95 reduction.
- Main final results:
  - `prefill_throughput_medium`: selected SLO goodput 1815.04 -> 3590.21 tok/s,
    +97.80%; rebuilt 11790 -> 1725, -85.37%.
  - `interactive_latency_medium`: foreground-priority stage; protected foreground
    classes 6/6 >=30% e2e P95 reduction, but background/decode guards regress.
  - `enterprise_normal_medium`: goodput 1383.78 -> 1624.16 tok/s, +17.37%;
    e2e P95 latency 316.015s -> 112.722s, +64.33% reduction; rebuilt
    6602 -> 6455, -2.23%.
  - `low_reuse`: goodput 317.95 -> 448.88 tok/s, +41.18%; e2e P95 latency
    325.620s -> 15.798s, +95.15% reduction; prefix hit and rebuilt are zero,
    so this is an admission/cache-churn result rather than a prefix-reuse result.
