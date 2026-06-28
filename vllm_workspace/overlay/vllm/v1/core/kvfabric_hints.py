# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Request-hint metadata for KVFabric scheduler and admission policies."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field


KVFABRIC_HINT_HEADERS = {
    "request_class": (
        "x-kvfabric-request-class",
        "x-kvfabric-class",
    ),
    "trace_request_id": (
        "x-kvfabric-trace-request-id",
        "x-kvfabric-trace-id",
    ),
    "tenant_id": (
        "x-kvfabric-tenant-id",
        "x-kvfabric-tenant",
    ),
    "family_id": (
        "x-kvfabric-family-id",
        "x-kvfabric-family",
    ),
    "cache_priority": (
        "x-kvfabric-cache-priority",
        "x-kvfabric-priority",
    ),
    "expected_reuse": (
        "x-kvfabric-expected-reuse",
        "x-kvfabric-reuse",
    ),
    "phase": (
        "x-kvfabric-phase",
    ),
    "burst": (
        "x-kvfabric-burst",
    ),
    "session_id": (
        "x-kvfabric-session-id",
        "x-kvfabric-session",
    ),
    "turn_index": (
        "x-kvfabric-turn-index",
        "x-kvfabric-turn",
    ),
    "slo_ms": (
        "x-kvfabric-slo-ms",
        "x-kvfabric-slo",
    ),
    "hint_confidence": (
        "x-kvfabric-hint-confidence",
        "x-kvfabric-confidence",
    ),
}

KVFABRIC_ALL_HINT_HEADERS = tuple(
    header
    for aliases in KVFABRIC_HINT_HEADERS.values()
    for header in aliases
)


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _token(value: object | None) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _header_get(headers: Mapping[str, str], name: str) -> str | None:
    try:
        value = headers.get(name)
    except AttributeError:
        value = None
    if value is not None:
        return _clean(value)

    target = name.lower()
    for key, candidate in headers.items():
        if str(key).lower() == target:
            return _clean(candidate)
    return None


def contains_kvfabric_hint_headers(headers: Mapping[str, str]) -> bool:
    return any(_header_get(headers, name) is not None
               for name in KVFABRIC_ALL_HINT_HEADERS)


def extract_kvfabric_hint_headers(
    headers: Mapping[str, str],
) -> Mapping[str, str]:
    output: dict[str, str] = {}
    for name in KVFABRIC_ALL_HINT_HEADERS:
        value = _header_get(headers, name)
        if value is not None:
            output[name] = value
    return output


def _bool_token(value: object | None) -> bool:
    return _token(value) in {"1", "true", "yes", "on", "y"}


def _derive_priority(request_class: str, expected_reuse: str, burst: bool) -> str:
    if "hot" in request_class or expected_reuse == "durable":
        return "high"
    if burst and "cold" in request_class:
        return "bypass"
    if "cold" in request_class or expected_reuse == "none":
        return "low"
    if "ambiguous" in request_class or expected_reuse == "transient":
        return "normal"
    return "normal"


def _derive_expected_reuse(request_class: str, phase: str | None) -> str:
    if "hot" in request_class:
        return "durable"
    if "ambiguous" in request_class or "transient" in request_class:
        return "transient"
    if "cold" in request_class or "unique" in request_class:
        return "none"
    if phase in {"warmup", "steady", "revisit"}:
        return "durable"
    return "unknown"


@dataclass(frozen=True)
class KVFabricRequestHints:
    request_class: str = "unknown"
    trace_request_id: str | None = None
    tenant_id: str | None = None
    family_id: str | None = None
    cache_priority: str = "normal"
    expected_reuse: str = "unknown"
    phase: str | None = None
    burst: bool = False
    session_id: str | None = None
    turn_index: int = 0
    slo_ms: int = 0
    hint_confidence: float = 1.0
    has_hints: bool = False

    @classmethod
    def from_headers(
        cls,
        headers: Mapping[str, str] | None,
    ) -> "KVFabricRequestHints":
        if not headers:
            return cls()

        values: dict[str, str | None] = {}
        for field_name, aliases in KVFABRIC_HINT_HEADERS.items():
            value = None
            for alias in aliases:
                value = _header_get(headers, alias)
                if value is not None:
                    break
            values[field_name] = value

        request_class = _token(values.get("request_class")) or "unknown"
        phase = _token(values.get("phase"))
        expected_reuse = _token(values.get("expected_reuse"))
        if expected_reuse not in {"durable", "transient", "none", "unknown"}:
            expected_reuse = None
        if expected_reuse is None:
            expected_reuse = _derive_expected_reuse(request_class, phase)

        burst = _bool_token(values.get("burst")) or "burst" in request_class
        cache_priority = _token(values.get("cache_priority"))
        if cache_priority not in {"high", "normal", "low", "bypass"}:
            cache_priority = _derive_priority(
                request_class,
                expected_reuse,
                burst,
            )

        tenant_id = _clean(values.get("tenant_id"))
        trace_request_id = _clean(values.get("trace_request_id"))
        family_id = _clean(values.get("family_id"))
        session_id = _clean(values.get("session_id"))
        try:
            turn_index = int(_clean(values.get("turn_index")) or 0)
        except ValueError:
            turn_index = 0
        try:
            slo_ms = int(float(_clean(values.get("slo_ms")) or 0))
        except ValueError:
            slo_ms = 0
        try:
            hint_confidence = float(_clean(values.get("hint_confidence")) or 1.0)
        except ValueError:
            hint_confidence = 1.0
        hint_confidence = min(max(hint_confidence, 0.0), 1.0)
        has_hints = any(value is not None for value in values.values())

        return cls(
            request_class=request_class,
            trace_request_id=trace_request_id,
            tenant_id=tenant_id,
            family_id=family_id,
            cache_priority=cache_priority,
            expected_reuse=expected_reuse,
            phase=phase,
            burst=burst,
            session_id=session_id,
            turn_index=max(turn_index, 0),
            slo_ms=max(slo_ms, 0),
            hint_confidence=hint_confidence,
            has_hints=has_hints,
        )

    @property
    def family_key(self) -> str | None:
        if self.family_id is None:
            return None
        tenant = self.tenant_id or "global"
        return f"{tenant}:{self.family_id}"

    @property
    def is_durable(self) -> bool:
        return self.expected_reuse == "durable" or self.cache_priority == "high"

    @property
    def is_low_reuse(self) -> bool:
        return self.expected_reuse == "none" or self.cache_priority in {
            "low",
            "bypass",
        }

    @property
    def is_transient(self) -> bool:
        return self.expected_reuse == "transient"

    def event_fields(self) -> dict[str, str | bool | None]:
        return {
            "hint_request_class": self.request_class,
            "hint_trace_request_id": self.trace_request_id,
            "hint_tenant_id": self.tenant_id,
            "hint_family_id": self.family_id,
            "hint_family_key": self.family_key,
            "hint_cache_priority": self.cache_priority,
            "hint_expected_reuse": self.expected_reuse,
            "hint_phase": self.phase,
            "hint_burst": self.burst,
            "hint_session_id": self.session_id,
            "hint_turn_index": self.turn_index,
            "hint_slo_ms": self.slo_ms,
            "hint_confidence": self.hint_confidence,
            "hint_has_hints": self.has_hints,
        }


@dataclass
class HintFamilyRuntime:
    family_key: str
    tenant_id: str | None = None
    family_id: str | None = None
    session_id: str | None = None
    first_seen_ns: int = 0
    last_seen_ns: int = 0
    request_count: int = 0
    scheduled_count: int = 0
    deferred_count: int = 0
    admission_limited_count: int = 0
    finished_count: int = 0
    prompt_tokens: int = 0
    prefix_hit_tokens: int = 0
    scheduled_tokens: int = 0
    output_tokens: int = 0
    class_counts: Counter[str] = field(default_factory=Counter)
    priority_counts: Counter[str] = field(default_factory=Counter)
    reuse_counts: Counter[str] = field(default_factory=Counter)
    last_request_class: str = "unknown"
    last_cache_priority: str = "normal"
    last_expected_reuse: str = "unknown"

    def observe_request(
        self,
        hints: KVFabricRequestHints,
        prompt_tokens: int,
        now_ns: int | None = None,
    ) -> None:
        now_ns = now_ns or time.monotonic_ns()
        if self.first_seen_ns == 0:
            self.first_seen_ns = now_ns
        self.last_seen_ns = now_ns
        self.tenant_id = hints.tenant_id or self.tenant_id
        self.family_id = hints.family_id or self.family_id
        self.session_id = hints.session_id or self.session_id
        self.request_count += 1
        self.prompt_tokens += max(prompt_tokens, 0)
        self.class_counts[hints.request_class] += 1
        self.priority_counts[hints.cache_priority] += 1
        self.reuse_counts[hints.expected_reuse] += 1
        self.last_request_class = hints.request_class
        self.last_cache_priority = hints.cache_priority
        self.last_expected_reuse = hints.expected_reuse

    def observe_lookup(self, hit_tokens: int, now_ns: int | None = None) -> None:
        self.last_seen_ns = now_ns or time.monotonic_ns()
        self.prefix_hit_tokens += max(hit_tokens, 0)

    def observe_schedule(
        self,
        scheduled_tokens: int,
        now_ns: int | None = None,
    ) -> None:
        self.last_seen_ns = now_ns or time.monotonic_ns()
        self.scheduled_count += 1
        self.scheduled_tokens += max(scheduled_tokens, 0)

    def observe_defer(self, now_ns: int | None = None) -> None:
        self.last_seen_ns = now_ns or time.monotonic_ns()
        self.deferred_count += 1

    def observe_admission_limit(self, now_ns: int | None = None) -> None:
        self.last_seen_ns = now_ns or time.monotonic_ns()
        self.admission_limited_count += 1

    def observe_finish(
        self,
        output_tokens: int,
        now_ns: int | None = None,
    ) -> None:
        self.last_seen_ns = now_ns or time.monotonic_ns()
        self.finished_count += 1
        self.output_tokens += max(output_tokens, 0)

    @property
    def hit_ratio(self) -> float:
        if self.prompt_tokens <= 0:
            return 0.0
        return self.prefix_hit_tokens / self.prompt_tokens

    def event_fields(self) -> dict[str, object]:
        return {
            "hint_family_key": self.family_key,
            "hint_tenant_id": self.tenant_id,
            "hint_family_id": self.family_id,
            "hint_session_id": self.session_id,
            "hint_family_request_count": self.request_count,
            "hint_family_scheduled_count": self.scheduled_count,
            "hint_family_deferred_count": self.deferred_count,
            "hint_family_admission_limited_count": (
                self.admission_limited_count
            ),
            "hint_family_finished_count": self.finished_count,
            "hint_family_prompt_tokens": self.prompt_tokens,
            "hint_family_prefix_hit_tokens": self.prefix_hit_tokens,
            "hint_family_hit_ratio": self.hit_ratio,
            "hint_family_last_request_class": self.last_request_class,
            "hint_family_last_cache_priority": self.last_cache_priority,
            "hint_family_last_expected_reuse": self.last_expected_reuse,
        }


class HintFamilyIndex:
    def __init__(self) -> None:
        self.families: dict[str, HintFamilyRuntime] = {}

    def clear(self) -> None:
        self.families.clear()

    def get(
        self,
        hints: KVFabricRequestHints | None,
    ) -> HintFamilyRuntime | None:
        if hints is None or hints.family_key is None:
            return None
        return self.families.get(hints.family_key)

    def observe_request(
        self,
        hints: KVFabricRequestHints,
        prompt_tokens: int,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        family_key = hints.family_key
        if family_key is None:
            return None
        runtime = self.families.get(family_key)
        if runtime is None:
            runtime = HintFamilyRuntime(
                family_key=family_key,
                tenant_id=hints.tenant_id,
                family_id=hints.family_id,
            )
            self.families[family_key] = runtime
        runtime.observe_request(hints, prompt_tokens, now_ns=now_ns)
        return runtime

    def observe_lookup(
        self,
        hints: KVFabricRequestHints | None,
        hit_tokens: int,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        runtime = self.get(hints)
        if runtime is not None:
            runtime.observe_lookup(hit_tokens, now_ns=now_ns)
        return runtime

    def observe_schedule(
        self,
        hints: KVFabricRequestHints | None,
        scheduled_tokens: int,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        runtime = self.get(hints)
        if runtime is not None:
            runtime.observe_schedule(scheduled_tokens, now_ns=now_ns)
        return runtime

    def observe_defer(
        self,
        hints: KVFabricRequestHints | None,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        runtime = self.get(hints)
        if runtime is not None:
            runtime.observe_defer(now_ns=now_ns)
        return runtime

    def observe_admission_limit(
        self,
        hints: KVFabricRequestHints | None,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        runtime = self.get(hints)
        if runtime is not None:
            runtime.observe_admission_limit(now_ns=now_ns)
        return runtime

    def observe_finish(
        self,
        hints: KVFabricRequestHints | None,
        output_tokens: int,
        now_ns: int | None = None,
    ) -> HintFamilyRuntime | None:
        runtime = self.get(hints)
        if runtime is not None:
            runtime.observe_finish(output_tokens, now_ns=now_ns)
        return runtime
