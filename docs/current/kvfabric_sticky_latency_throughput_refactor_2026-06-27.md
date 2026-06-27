# Sticky Conversation Latency and Throughput Refactor

Date: 2026-06-27

This note follows the Sticky Conversation fairness run
`2026-06-26_230155_qwen3_5_27b_qwen3_5_27b_sticky_conversation_trace_4h_trace_long`.
That run fixed the timeout failures from the previous Sticky benchmark, but it
also showed a new scheduler problem: cold requests no longer failed, yet they
waited too long behind hot sticky traffic.

## Result Review

The fairness run completed all policies with zero errors:

| Policy | Completed | Errors | Total tok/s | Avg latency | P95 latency | Rebuilt vs LRU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lru | 2597 | 0 | 1202.12 | 65.423s | 115.472s | baseline |
| shared_aware | 2597 | 0 | 1202.23 | 62.852s | 126.529s | -81.23% |
| family_protect | 2597 | 0 | 1195.05 | 63.876s | 126.057s | -81.09% |

The positive result is clear: the KVFabric policies kept useful prefixes in
cache and cut rebuilt blocks by about 81%. Hot reusable classes also became much
faster:

| Class | LRU avg | shared_aware avg | family_protect avg |
| --- | ---: | ---: | ---: |
| agent_tool_loop | 59.327s | 29.562s | 29.419s |
| deep_multi_turn_chat | 59.093s | 32.870s | 33.077s |
| long_doc_followup_qa | 75.701s | 42.204s | 42.496s |

The weak point is the low-reuse tail:

| Class | LRU p95 | shared_aware p95 | family_protect p95 |
| --- | ---: | ---: | ---: |
| cold_rag_noise | 104.849s | 919.723s | 933.639s |
| decode_heavy_noise | 183.875s | 995.016s | 1021.171s |

The bounded defer patch prevented timeouts, but positive promotion still kept
moving hot requests ahead of old cold requests. The result was acceptable
completion count and strong cache evidence, but not acceptable tail latency.

## Design

The scheduler now has a head-of-line aging guard for positive promotion.

Before this patch, KVFabric could promote a hot sticky request from deeper in
the waiting queue whenever the score margin was large enough. That is useful
under pressure, but it can repeatedly bypass an old queue head. The new guard
checks the age of the current head request before promoting another request
above it.

New controls:

- `KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS`
- `KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS`

The low-reuse threshold is separate because the observed tail problem was
strongest for `cold_rag_noise`. In the new Sticky launcher:

- general head age guard: `90000 ms`
- low-reuse head age guard: `45000 ms`
- low-reuse defer age cap: `30000 ms`
- general defer age cap: `90000 ms`
- max defer per step: `1`
- max defer count: `2`
- low-reuse max defer count: `1`

This keeps the first part of the queue flexible for hot-prefix batching, then
falls back to FIFO service once a request has waited long enough.

The lifecycle log records `request_promotion_skipped` when the age guard blocks
a positive promotion. The summary includes:

- `request_promotion_skipped_events`
- `scheduler_promotion_skipped_reasons`
- `scheduler_promotion_skipped_hint_classes`
- average and max head age for promotion skips

These counters should rise in the new run. That is expected: they show the
scheduler is protecting old head requests instead of only promoting hot work.

## Experiment Change

The previous Sticky trace was useful for latency and rebuilt-block analysis, but
it was not a good throughput proof. It was a fixed open-loop replay where all
policies eventually completed the same measured requests. In that setup, total
tok/s tends to converge unless one policy leaves a large unfinished tail.

The updated Sticky trace keeps the same workload family but raises pressure:

- request rate: `0.45 -> 0.62`
- max in-flight: `40 -> 64`
- max running sequences: `16 -> 18`
- max batched tokens: `16384 -> 20480`
- timeout: `1200s -> 1500s`
- SLO: `240s`

The trace load generator now reports latency-aware goodput:

- `goodput_total_tokens`
- `goodput_total_tokens_per_second`
- `slo_pass`
- `slo_miss`
- `slo_miss_rate`

This makes the benchmark less dependent on final drain time. Under high
pressure, a policy that keeps hot prefixes warm and avoids starving cold work
should deliver more tokens inside the SLO window.

## Expected Evidence

The new Sticky 4h run should be judged with these checks:

1. Errors remain zero or near zero.
2. `shared_aware` and `family_protect` still reduce rebuilt-from-eviction blocks
   sharply versus LRU.
3. Hot reusable classes keep lower average and p95 latency than LRU.
4. Cold and decode-heavy class p95 latency should drop materially from the
   900-1000s range.
5. `request_promotion_skipped_events` should appear for low-reuse or old queue
   head requests.
6. Goodput tok/s should become more meaningful than total tok/s; this is the
   main metric for throughput under SLO.

If cold/decode tail latency is still too high, the next step is a small FIFO
reserve: allow at least one old low-reuse request to enter every N scheduling
steps when queue pressure stays red.
