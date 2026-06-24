# KVFabric Hint-Aware Scheduler and Admission Refactor

Date: 2026-06-22
Target vLLM: 0.22.1
Primary remote target: qwen3_5_27b / Qwen/Qwen3.5-27B-FP8 on 2 x RTX 3090 24GB

## Background

The current 0.22.1 overlay already provides lifecycle observation, JSONL events,
explicit block-hash prefix-family lineage, rebuilt-from-eviction regret
tracking, family-aware victim selection, risk-aware admission, and a simple
FCFS cold-miss deferral path. The 10 hour qwen3_5_27b pressure run confirmed
that this is effective at cache quality: shared-aware and family-protect
policies reduced rebuilt-from-eviction regret by roughly two orders of
magnitude. Throughput improved by about 10%, not the target 30%.

The main reason is workload visibility. The server currently infers request
intent only after local prefix lookup. That means the scheduler and admission
logic cannot distinguish a durable hot workflow family from a transient
campaign-like family until after it has already consumed queue position and
some cache space. In the long run, only about 13% of prompt tokens were prefix
hits, so improving victim selection alone cannot produce a 30% end-to-end
throughput gain on the tested mix.

The next design therefore keeps the low-risk Python control-plane approach but
adds request hints and request-family runtime state. The benchmark generator
already has realistic metadata such as hot family, cold RAG, transient
ambiguous family, burst state, tenant, family, and phase. This refactor carries
that metadata through HTTP headers into vLLM's Request object and uses it for
scheduler deferral, cache admission, and lifecycle analysis.

## Goals

1. Preserve vLLM 0.22.1 compatibility and avoid CUDA/kernel changes.
2. Add a stable, explicit request-hint channel for benchmark and future serving
   probes.
3. Track request lifecycle with class, tenant, family, priority, expected
   reuse, and phase.
4. Maintain runtime family hotness independently from block-hash lineage, so
   cold miss decisions can still use client-visible family identity.
5. Improve scheduler behavior under pressure by delaying low-value cold long
   misses when the queue contains likely reusable work.
6. Improve cache admission by caching fewer blocks for explicitly low-reuse
   cold requests, while preserving durable family anchors and revisits.
7. Emit enough events to explain why a policy improved or regressed.
8. Keep every new behavior guarded by environment variables.

## Non-Goals

1. No KV layout changes and no CUDA kernel changes.
2. No semantic change to prompt contents in benchmark workloads.
3. No hard dependency on OpenTelemetry tracing being enabled.
4. No attempt to guarantee a 30% gain on a workload whose reusable token share
   is too low. The target is to create the control-plane mechanisms needed to
   reach that gain on realistic high-pressure reusable mixes and to expose why
   a run falls short.

## Architecture

### Request Hint Channel

The load generator maps existing request `meta` fields to HTTP headers:

- `x-kvfabric-request-class`: hot_family, cold_rag, cold_rag_burst,
  ambiguous_short_family, etc.
- `x-kvfabric-tenant-id`: stable tenant identifier.
- `x-kvfabric-family-id`: stable workload-visible family identifier.
- `x-kvfabric-cache-priority`: high, normal, low, or bypass.
- `x-kvfabric-expected-reuse`: durable, transient, none, or unknown.
- `x-kvfabric-phase`: warmup, steady, revisit, burst, etc.
- `x-kvfabric-burst`: true or false.

The OpenAI serving layer extracts those headers even when normal tracing is
disabled, stores them in `trace_headers`, and the scheduler reads them from
`Request.trace_headers`. This deliberately reuses the existing Request field to
avoid changing public request schemas or engine RPC message shapes.

### Request Runtime Metadata

`KVFabricRequestHints` normalizes headers and derives defaults:

- hot family classes default to high priority and durable reuse.
- cold RAG classes default to low priority and no expected reuse.
- burst cold RAG defaults to bypass priority under pressure.
- ambiguous short families default to normal priority and transient reuse.

`RequestMeta` is extended with hint fields and scheduling counters. Lookup,
schedule, defer, admission-limit, and finish events all include the same hint
fields, so long-run logs can be joined by request id without reconstructing
state from prompt text.

### Hint Family Runtime

`HintFamilyRuntime` tracks client-visible family behavior:

- total requests and recent sequence.
- total prefix hit tokens and prompt tokens.
- scheduled, deferred, limited, and finished counters.
- regret/rebuild counter propagated from block-family regret when available.
- last pressure state and last event timestamps.

This complements block-hash `PrefixFamilyIndex`. The block index answers
"which cached prefix tree does this block belong to?" The hint family index
answers "what does the workload say this request family is, even before its
prefix is cached?"

### Scheduler Policy

The scheduler still uses FCFS as the base policy. Under non-LRU KVFabric
policies, it may rotate a waiting request to the tail if all conditions hold:

1. cache pressure or eviction-risk pressure is at least the configured
   threshold;
2. the request is a cold or nearly-cold long prefill;
3. the request hint says low priority, bypass priority, no expected reuse, or
   burst cold traffic;
4. it has not already been deferred in the same scheduling pass;
5. the defer budget for the step is not exhausted.

Durable or high-priority requests are not deferred merely because they miss the
cache. This is important for family warmup: a durable family must be allowed to
build anchors before it can hit.

### Admission Policy

Admission becomes hint-aware:

- high-priority durable families are allowed to cache full blocks unless risk
  is severe and there is no prefix hit.
- transient families cache anchor/discovery blocks under yellow or worse
  pressure.
- low/no-reuse cold requests are capped more aggressively.
- bypass requests cache only the minimum anchor/discovery budget under pressure.
- short requests remain unrestricted because the overhead of admission is not
  worth the possible savings.

The existing risk-aware free-list head scan remains the pressure sensor. Hints
do not replace pressure; they change which requests receive cache space when
pressure exists.

### Metrics and Logs

New JSONL events:

- `request_hints_observed`
- `hint_family_observed`
- `request_deferred` with hint fields and defer reason
- `cache_admission_limited` with hint fields and admission reason
- `request_scheduled` with hint fields
- `request_finished` with hint fields

The lifecycle summarizer reports:

- hint coverage;
- request class distribution;
- cache-priority and expected-reuse distribution;
- top hint families by requests, hit tokens, deferrals, and admission limits;
- defer and admission reasons.

## Benchmark Design

The benchmark should not change prompts to favor KVFabric. Instead it should:

1. keep the existing mixed realistic pressure prompt mix;
2. emit explicit metadata already known by a real gateway or application;
3. run enough concurrency to keep both 3090s busy;
4. include hot durable families, transient shared-looking families, unique cold
   RAG, and burst cold traffic;
5. collect rolling metrics and raw lifecycle events throughout the run;
6. run LRU, shared-aware, and family-protect with identical request selection
   seeds.

The short validation run can be 300-600 seconds. The final performance run
should be a multi-hour run once compile and smoke checks pass.

## Environment Gates

- `KVFABRIC_HINTS=1`: enable parsing and use of request hints.
- `KVFABRIC_HINT_HEADER_TRACE=1`: emit hint extraction through OpenAI serving.
- `KVFABRIC_HINT_ADMISSION=1`: use hints in cache admission.
- `KVFABRIC_HINT_SCHEDULER=1`: use hints in scheduler deferral.
- `KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS`: cap for low/no-reuse prompts.
- `KVFABRIC_HINT_LOW_REUSE_MIN_CACHE_BLOCKS`: minimum cached blocks for
  low/no-reuse prompts; the default is 0 because qwen3_5_27b uses a large
  784-token attention block and one cached cold block is enough to pollute the
  prefix cache under pressure.
- `KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS`: cap for bypass-priority burst cold
  prompts.
- `KVFABRIC_HINT_BYPASS_MIN_CACHE_BLOCKS`: minimum cached blocks for bypass
  prompts; default 0.
- `KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS`: cap for transient families.
- `KVFABRIC_HINT_DURABLE_MIN_HIT_TOKENS`: hit threshold for unrestricted durable
  reuse.

All gates default on when `KVFABRIC_LIFECYCLE=1` except the serving extraction
gate, which is harmless without matching headers.

## Failure Modes and Mitigations

- Header extraction could accidentally interfere with real tracing. Mitigation:
  KVFabric headers are extracted separately and normal W3C trace headers still
  follow the original tracing-enabled logic.
- Hints can be wrong. Mitigation: hints bias only admission and deferral under
  pressure; they do not make correctness decisions.
- Over-deferral can increase tail latency. Mitigation: step-level defer budget,
  per-request single defer per pass, and no defer for durable/high-priority
  requests.
- Low-reuse caps can hurt future reuse if the classifier is too aggressive.
  Mitigation: ambiguous/transient classes get a larger discovery budget than
  unique cold RAG, and metrics expose `cache_admission_limited` by class.
- Extra JSONL volume can affect long runs. Mitigation: buffered writes already
  exist, and hint events are one per request plus policy events.

## Verification Plan

1. Local compile:
   `python -m py_compile` on all new overlay files and benchmark scripts.
2. Local metadata unit smoke:
   expand the realistic config and verify headers are generated for all classes.
3. Local vLLM smoke on Qwen/Qwen3.5-2B if GPU memory is available.
4. Remote deploy into `.venv_kvfabric_0221` using the existing overlay apply
   script.
5. Remote short policy run:
   300-600 seconds for LRU, shared-aware, and family-protect with identical
   realistic pressure config and request seed.
6. Analyze:
   compare total token throughput, latency, prefix hit share, rebuilt-from-
   eviction regret, hint coverage, defer counts, admission-limit counts, and
   class-level throughput.
7. If short run is stable and improves, launch a longer multi-hour run.

## Expected Outcome

This refactor should produce a more measurable improvement when the queue has
mixed reusable and cold traffic under pressure. It may not by itself achieve
30% on the existing 10 hour mix because only a minority of tokens are reusable.
The important result is a better control surface and enough telemetry to decide
whether the next gain should come from workload shaping, chunk-level reuse,
batch affinity, or deeper scheduler changes.
