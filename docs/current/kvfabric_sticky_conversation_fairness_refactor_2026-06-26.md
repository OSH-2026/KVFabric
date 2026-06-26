# Sticky Conversation Fairness Refactor

Date: 2026-06-26

This note records the fix for the first `qwen3_5_27b_sticky_conversation_trace_4h`
run and the updated Sticky Conversation benchmark profile. The goal is to keep
the workload under high pressure while avoiding starvation of low-reuse requests.

## Background

The Sticky Conversation trace is intended to stress a common serving pattern:
long multi-turn chats, long-document follow-up questions, tool-loop sessions,
and a smaller amount of cold RAG or decode-heavy traffic. The useful cache
behavior is concentrated in the sticky sessions. A good KV cache policy should
keep those hot prefixes warm, reduce rebuilds, and lower latency for the
repeated-turn traffic.

The first 4h Sticky run showed that the current policy can protect reusable
prefixes, but it also pushed low-reuse requests too far back in the queue:

| Policy | Completed | Errors | Total tok/s | Avg latency | P95 latency | Prefix hit | Rebuilt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lru | 2597 | 0 | 1072.69 | 66.660s | 99.489s | 0.10% | 8594 |
| shared_aware | 2528 | 69 | 1087.30 | 37.706s | 90.684s | 2.55% | 1483 |
| family_protect | 2524 | 73 | 1091.97 | 36.403s | 78.529s | 1.88% | 1424 |

The errors were `ReadTimeout` failures. They were concentrated in
`cold_rag_noise` and `decode_heavy_noise`:

| Policy | cold_rag_noise errors | decode_heavy_noise errors |
| --- | ---: | ---: |
| shared_aware | 50 | 19 |
| family_protect | 48 | 25 |

The lifecycle logs explain the pattern. For `shared_aware`, there were 354
scheduler deferrals and 2428 promotions. Deferrals were mostly
`hint_low_reuse_cold_miss`; promotions were almost all sticky classes:
`deep_multi_turn_chat`, `long_doc_followup_qa`, and `agent_tool_loop`.
`family_protect` showed the same shape. The policies improved useful cache
retention and reduced rebuilt blocks by more than 80%, but the scheduler had no
cross-step fairness bound. A request could be deferred repeatedly if it stayed
cold, long, and low priority while the system remained under pressure.

## Problem

The earlier scheduler behavior had two incomplete parts:

1. Positive selection worked: hot sticky requests were promoted when hints and
   estimated hit tokens indicated high reuse.
2. Negative selection was too open-ended: cold or low-reuse requests could be
   deferred again and again as long as pressure stayed high.

That creates an unfair high-pressure trace. The benchmark then measures a mix of
real KV-cache improvement and avoidable queue starvation. For a server workload,
low-reuse traffic should not dominate the cache, but it still needs bounded
service time. Enterprise users send one-off RAG questions, exports, summaries,
and decode-heavy jobs alongside sticky sessions. Dropping or timing them out is
not an acceptable way to show throughput improvement.

## Design

The fix keeps the useful part of the scheduler and bounds the risky part.

Positive selection remains active for Sticky Conversation:

- `KVFABRIC_SCHEDULER_AFFINITY=positive`
- scan up to 32 waiting requests
- enable hit-aware scoring
- keep the session-turn bonus for sticky conversations

Negative defer now has fairness limits:

- `KVFABRIC_SCHEDULER_DEFER_MAX_COUNT=3`
- `KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT=1`
- `KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS=180000`
- `KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS=60000`

Low-reuse classes get stricter bounds because they were the source of most
timeouts. They can still yield once during a red-pressure moment, but after that
the scheduler lets them run. General cold misses can yield up to three times or
up to three minutes of request age.

The defer threshold is also raised for Sticky:

- previous 4h suite default: `KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO=0.50`
- new Sticky profile: `KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO=0.65`
- low-reuse delta reduced from `0.10` to `0.05`

This keeps defer as a red-pressure tool instead of a broad default reaction.

## Code Changes

The lifecycle tracker now records enough request state to bound repeated
deferrals:

- creates request metadata before scheduler decisions when needed
- tracks request age from the first observed request event
- uses `RequestMeta.deferred_count` across scheduler steps
- emits `request_defer_skipped` when a request would have been deferred but a
  fairness cap lets it proceed

The new event includes:

- `skip_reason`
- `defer_reason`
- `request_age_ms`
- `deferred_count`
- eviction risk and threshold
- hint class, priority, expected reuse, tenant, session, and family fields

The lifecycle summary now reports:

- `request_defer_skipped_events`
- `scheduler_defer_skipped_reasons`
- `scheduler_defer_skipped_defer_reasons`
- `scheduler_defer_skipped_hint_classes`
- average and max risk/age for defer skips

The remote benchmark summary and acceptance analysis include defer-skip counts,
so the result can show whether the scheduler bounded starvation while still
promoting reusable work.

The trace load generator also records `error_types` in `metrics.json` and in
each request class metric. This makes timeout regressions visible in the summary
without opening the raw sampled outputs.

## Updated Sticky Experiment

The 4h and 12h Sticky configs keep the same trace structure:

- profile: `conversation_sticky`
- request rate: `0.45`
- seed: `20260624`
- load mode: `stress_90`
- hint regime: `partial_hints`
- max model length: `4096`

The serving/loadgen profile is more explicit:

- `TRACE_BENCH_MAX_NUM_SEQS=16`
- `TRACE_BENCH_MAX_NUM_BATCHED_TOKENS=16384`
- `TRACE_BENCH_MAX_IN_FLIGHT=40`
- `TRACE_BENCH_TIMEOUT_SECONDS=1200`

This is still a high-pressure run. The larger in-flight window keeps the server
backlogged, and the larger batch limits give vLLM room to use batching rather
than turning every long request into a timeout. The timeout increase is a guard
against false failures in the pressure tail; it is not the main fix. The main
fix is bounded defer.

The Sticky wrappers set these parameters directly:

- `run_remote_27b_sticky_conversation_trace_4h_benchmark.sh`
- `run_remote_27b_sticky_conversation_trace_12h_benchmark.sh`

The generic enterprise trace launcher only passes through neutral defaults, so
Enterprise Mixed is not changed by this patch.

## Expected Result

The new 4h rerun should be judged by four checks:

1. Correctness: `errors` should fall to zero or near zero for `shared_aware` and
   `family_protect`. Any remaining errors should be inspected by request class.
2. Cache value: rebuilt-from-eviction should stay far below LRU, ideally close
   to the previous 80% reduction.
3. Scheduler evidence: promotions should remain concentrated in sticky reusable
   classes, and defer-skip events should appear mostly for `cold_rag_noise` or
   `decode_heavy_noise`.
4. Performance: latency should stay below LRU for sticky classes. Throughput may
   not jump dramatically in a fixed open-loop trace, but total tok/s and goodput
   should not regress materially. If errors disappear while rebuilt blocks stay
   low, the architecture is behaving more like a real service.

## Follow-up

If the rerun still has errors, the next changes should focus on queue aging:

- add an explicit age bonus to `positive_request_score`
- expose per-class waiting time in the loadgen metrics
- add a small FIFO reserve for low-reuse classes when pressure is red

If the rerun has no errors but throughput gain remains small, the next work is
to make the scheduler more proactive:

- batch requests from the same sticky family together
- use family-level recent hit rate in promotion scoring
- reduce over-protection in `family_protect` when a family has stopped receiving
  hits
- use rebuilt-from-eviction feedback to adjust retain scores over time
