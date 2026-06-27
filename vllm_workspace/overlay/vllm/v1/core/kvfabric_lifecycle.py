# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""KVFabric lifecycle side table and JSONL event stream.

This module is intentionally low-intrusion: by default it is disabled and does
not affect vLLM cache behavior. Set KVFABRIC_LIFECYCLE=1 to maintain the side
table, and KVFABRIC_LIFECYCLE_LOG_PATH=/path/events.jsonl to emit events.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from heapq import nsmallest
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vllm.v1.core.kvfabric_family import PrefixFamilyIndex
from vllm.v1.core.kvfabric_hints import (
    HintFamilyIndex,
    KVFabricRequestHints,
)

if TYPE_CHECKING:
    from vllm.v1.core.kv_cache_utils import BlockHashWithGroupId, KVCacheBlock


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_tokens(name: str, default: str = "") -> tuple[str, ...]:
    text = os.environ.get(name, default).strip().lower()
    if not text:
        return ()
    return tuple(
        item.strip()
        for item in text.replace(",", " ").split()
        if item.strip()
    )


def _hash_to_hex(block_hash: "BlockHashWithGroupId | None") -> str | None:
    if block_hash is None:
        return None
    return bytes(block_hash).hex()


@dataclass
class LifecycleBlockMeta:
    block_id: int
    block_hash: str | None = None
    prefix_depth: int = 0
    ref_count: int = 0
    hit_count: int = 0
    share_degree: int = 0
    branch_factor: int = 0
    recompute_cost_tokens: int = 0
    state: str = "FREE"
    created_time_ns: int = 0
    last_access_time_ns: int = 0
    family_id: int | None = None
    root_hash: str | None = None
    parent_hash: str | None = None
    family_hit_count: int = 0
    family_branch_count: int = 0
    family_regret_count: int = 0
    protected_depth: int = 0

    def retain_score(
        self,
        use_reuse: bool = True,
        use_prefix: bool = True,
        use_recompute: bool = True,
    ) -> float:
        reused = self.hit_count > 0 or self.share_degree > 1
        reuse_value = (
            8.0 * self.hit_count
            + 6.0 * max(self.share_degree - 1, 0)
            + 3.0 * self.branch_factor
        ) if use_reuse else 0.0
        anchor_value = (
            8.0 / max(self.prefix_depth, 1)
            if reused and use_prefix
            else 0.0
        )
        recompute_value = (
            0.04 * self.recompute_cost_tokens
            if reused and use_recompute
            else 0.0
        )
        return (
            reuse_value
            + anchor_value
            + recompute_value
        )


@dataclass
class EvictedShadow:
    block_hash: str
    block_id: int
    prefix_depth: int
    hit_count: int
    share_degree: int
    branch_factor: int
    recompute_cost_tokens: int
    retain_score: float
    evicted_time_ns: int
    family_id: int | None = None
    root_hash: str | None = None
    parent_hash: str | None = None


@dataclass
class RequestMeta:
    request_id: str
    prompt_tokens: int = 0
    prefix_hit_tokens: int = 0
    first_miss_depth: int = 0
    max_cache_hit_length: int = 0
    request_class: str = "unknown"
    family_id: int | None = None
    arrival_time_ns: int = 0
    last_update_time_ns: int = 0
    finish_time_ns: int = 0
    computed_tokens: int = 0
    output_tokens: int = 0
    max_output_tokens: int = 0
    state: str = "LOOKUP"
    hint_request_class: str = "unknown"
    hint_tenant_id: str | None = None
    hint_family_id: str | None = None
    hint_family_key: str | None = None
    hint_cache_priority: str = "normal"
    hint_expected_reuse: str = "unknown"
    hint_phase: str | None = None
    hint_burst: bool = False
    hint_session_id: str | None = None
    hint_turn_index: int = 0
    hint_slo_ms: int = 0
    hint_confidence: float = 1.0
    hint_has_hints: bool = False
    deferred_count: int = 0
    admission_limited_count: int = 0


class KVFabricLifecycleTracker:
    """Tracks OS-style KV block lifecycle metadata for KVFabric experiments."""

    def __init__(self, enabled: bool, log_path: str | None = None) -> None:
        self.enabled = enabled
        self.log_path = Path(log_path).expanduser() if log_path else None
        self.eviction_policy = os.environ.get(
            "KVFABRIC_EVICTION_POLICY", "lru"
        ).strip().lower()
        self.enable_family_tree = os.environ.get(
            "KVFABRIC_ENABLE_FAMILY_TREE", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.enable_request_meta = os.environ.get(
            "KVFABRIC_ENABLE_REQUEST_META", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.enable_hints = os.environ.get(
            "KVFABRIC_HINTS", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.hint_admission = os.environ.get(
            "KVFABRIC_HINT_ADMISSION", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.hint_scheduler = os.environ.get(
            "KVFABRIC_HINT_SCHEDULER", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.hint_low_reuse_discovery_tokens = int(
            os.environ.get("KVFABRIC_HINT_LOW_REUSE_DISCOVERY_TOKENS", "0")
        )
        self.hint_low_reuse_min_cache_blocks = int(
            os.environ.get("KVFABRIC_HINT_LOW_REUSE_MIN_CACHE_BLOCKS", "0")
        )
        self.hint_bypass_discovery_tokens = int(
            os.environ.get("KVFABRIC_HINT_BYPASS_DISCOVERY_TOKENS", "0")
        )
        self.hint_bypass_min_cache_blocks = int(
            os.environ.get("KVFABRIC_HINT_BYPASS_MIN_CACHE_BLOCKS", "0")
        )
        self.hint_transient_discovery_tokens = int(
            os.environ.get("KVFABRIC_HINT_TRANSIENT_DISCOVERY_TOKENS", "768")
        )
        self.hint_durable_discovery_tokens = int(
            os.environ.get("KVFABRIC_HINT_DURABLE_DISCOVERY_TOKENS", "1536")
        )
        self.hint_durable_min_hit_tokens = int(
            os.environ.get("KVFABRIC_HINT_DURABLE_MIN_HIT_TOKENS", "256")
        )
        self.hint_defer_low_reuse_risk_delta = float(
            os.environ.get("KVFABRIC_HINT_DEFER_LOW_REUSE_RISK_DELTA", "0.10")
        )
        self.scheduler_trace = os.environ.get(
            "KVFABRIC_SCHEDULER_TRACE", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.admission_policy = os.environ.get(
            "KVFABRIC_ADMISSION_POLICY", "auto"
        ).strip().lower()
        self.admission_min_free_ratio = float(
            os.environ.get("KVFABRIC_ADMISSION_MIN_FREE_RATIO", "0.20")
        )
        self.admission_anchor_blocks = int(
            os.environ.get("KVFABRIC_ADMISSION_ANCHOR_BLOCKS", "8")
        )
        self.admission_cold_discovery_blocks = int(
            os.environ.get("KVFABRIC_ADMISSION_COLD_DISCOVERY_BLOCKS", "0")
        )
        self.admission_cold_discovery_tokens = int(
            os.environ.get("KVFABRIC_ADMISSION_COLD_DISCOVERY_TOKENS", "768")
        )
        self.admission_min_prompt_tokens = int(
            os.environ.get("KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS", "800")
        )
        self.admission_reuse_min_hit_tokens = int(
            os.environ.get("KVFABRIC_ADMISSION_REUSE_MIN_HIT_TOKENS", "512")
        )
        self.admission_use_eviction_risk = os.environ.get(
            "KVFABRIC_ADMISSION_USE_EVICTION_RISK", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        self.admission_limit_cold_miss = os.environ.get(
            "KVFABRIC_ADMISSION_LIMIT_COLD_MISS", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.admission_head_window = int(
            os.environ.get("KVFABRIC_ADMISSION_HEAD_WINDOW", "1024")
        )
        self.admission_risk_yellow_ratio = float(
            os.environ.get("KVFABRIC_ADMISSION_RISK_YELLOW_RATIO", "0.35")
        )
        self.admission_risk_orange_ratio = float(
            os.environ.get("KVFABRIC_ADMISSION_RISK_ORANGE_RATIO", "0.55")
        )
        self.admission_risk_red_ratio = float(
            os.environ.get("KVFABRIC_ADMISSION_RISK_RED_RATIO", "0.75")
        )
        self.scheduler_affinity = os.environ.get(
            "KVFABRIC_SCHEDULER_AFFINITY", "risk"
        ).strip().lower()
        self.scheduler_defer_min_prompt_tokens = int(
            os.environ.get(
                "KVFABRIC_SCHEDULER_DEFER_MIN_PROMPT_TOKENS",
                str(self.admission_min_prompt_tokens),
            )
        )
        self.scheduler_defer_min_waiting = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_MIN_WAITING", "2")
        )
        self.scheduler_defer_min_risk_ratio = float(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_MIN_RISK_RATIO", "0.55")
        )
        self.scheduler_defer_max_per_step = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_MAX_PER_STEP", "4")
        )
        self.scheduler_defer_max_count = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_MAX_COUNT", "0")
        )
        self.scheduler_defer_low_reuse_max_count = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_COUNT", "0")
        )
        self.scheduler_defer_max_age_ms = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_MAX_AGE_MS", "0")
        )
        self.scheduler_defer_low_reuse_max_age_ms = int(
            os.environ.get("KVFABRIC_SCHEDULER_DEFER_LOW_REUSE_MAX_AGE_MS", "0")
        )
        self.scheduler_positive_scan_window = int(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_SCAN_WINDOW", "0")
        )
        self.scheduler_positive_min_risk_ratio = float(
            os.environ.get(
                "KVFABRIC_SCHEDULER_POSITIVE_MIN_RISK_RATIO",
                str(self.scheduler_defer_min_risk_ratio),
            )
        )
        self.scheduler_positive_score_margin = float(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_SCORE_MARGIN", "4.0")
        )
        self.scheduler_positive_max_per_step = int(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_MAX_PER_STEP", "4")
        )
        self.scheduler_positive_hit_aware = os.environ.get(
            "KVFABRIC_SCHEDULER_POSITIVE_HIT_AWARE", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.scheduler_positive_hit_topk = int(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_HIT_TOPK", "4")
        )
        self.scheduler_positive_hit_weight = float(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_HIT_WEIGHT", "0.004")
        )
        self.scheduler_positive_hit_max_bonus = float(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_HIT_MAX_BONUS", "18.0")
        )
        self.scheduler_positive_session_turn_bonus = float(
            os.environ.get("KVFABRIC_SCHEDULER_POSITIVE_SESSION_TURN_BONUS", "1.5")
        )
        self.scheduler_head_age_guard_ms = int(
            os.environ.get("KVFABRIC_SCHEDULER_HEAD_AGE_GUARD_MS", "0")
        )
        self.scheduler_low_reuse_head_age_guard_ms = int(
            os.environ.get("KVFABRIC_SCHEDULER_LOW_REUSE_HEAD_AGE_GUARD_MS", "0")
        )
        self.scheduler_latency_protected_classes = _env_tokens(
            "KVFABRIC_SCHEDULER_LATENCY_PROTECTED_CLASSES"
        )
        self.scheduler_latency_protected_min_output_tokens = int(
            os.environ.get(
                "KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_OUTPUT_TOKENS",
                "512",
            )
        )
        self.scheduler_latency_protected_head_guard_ms = int(
            os.environ.get(
                "KVFABRIC_SCHEDULER_LATENCY_PROTECTED_HEAD_GUARD_MS",
                "0",
            )
        )
        self.scheduler_latency_protected_promote_age_ms = int(
            os.environ.get(
                "KVFABRIC_SCHEDULER_LATENCY_PROTECTED_PROMOTE_AGE_MS",
                "0",
            )
        )
        self.scheduler_latency_protected_min_risk_ratio = float(
            os.environ.get(
                "KVFABRIC_SCHEDULER_LATENCY_PROTECTED_MIN_RISK_RATIO",
                "0.0",
            )
        )
        self.protect_min_hit_count = int(
            os.environ.get("KVFABRIC_PROTECT_MIN_HIT_COUNT", "1")
        )
        self.protect_min_share_degree = int(
            os.environ.get("KVFABRIC_PROTECT_MIN_SHARE_DEGREE", "2")
        )
        self.protect_min_branch_factor = int(
            os.environ.get("KVFABRIC_PROTECT_MIN_BRANCH_FACTOR", "1")
        )
        self.protect_min_family_hits = int(
            os.environ.get("KVFABRIC_PROTECT_MIN_FAMILY_HITS", "2")
        )
        self.protect_min_family_branches = int(
            os.environ.get("KVFABRIC_PROTECT_MIN_FAMILY_BRANCHES", "1")
        )
        self.protected_depth_floor = int(
            os.environ.get("KVFABRIC_PROTECTED_DEPTH", "2")
        )
        self.pressure_yellow_ratio = float(
            os.environ.get("KVFABRIC_PRESSURE_YELLOW_RATIO", "0.30")
        )
        self.pressure_orange_ratio = float(
            os.environ.get("KVFABRIC_PRESSURE_ORANGE_RATIO", "0.18")
        )
        self.pressure_red_ratio = float(
            os.environ.get("KVFABRIC_PRESSURE_RED_RATIO", "0.08")
        )
        self.log_buffer_size = int(
            os.environ.get("KVFABRIC_LOG_BUFFER_SIZE", "256")
        )
        self.eviction_candidate_window_min = int(
            os.environ.get("KVFABRIC_EVICTION_CANDIDATE_WINDOW_MIN", "256")
        )
        self.eviction_candidate_window_multiplier = int(
            os.environ.get("KVFABRIC_EVICTION_CANDIDATE_WINDOW_MULTIPLIER", "8")
        )
        self.eviction_candidate_window_max = int(
            os.environ.get("KVFABRIC_EVICTION_CANDIDATE_WINDOW_MAX", "256")
        )
        self.eviction_rank_min_score = float(
            os.environ.get("KVFABRIC_EVICTION_RANK_MIN_SCORE", "0.0")
        )
        self.rank_log_candidates = _env_enabled("KVFABRIC_RANK_LOG_CANDIDATES")
        ablation = os.environ.get("KVFABRIC_RETAIN_ABLATION", "").strip().lower()
        ablated = {
            item.strip()
            for item in ablation.replace(",", " ").split()
            if item.strip()
        }
        self.retain_use_reuse = "reuse" not in ablated
        self.retain_use_prefix = "prefix" not in ablated
        self.retain_use_recompute = "recompute" not in ablated
        self.blocks: dict[int, LifecycleBlockMeta] = {}
        self.evicted_shadows: dict[str, EvictedShadow] = {}
        self.request_prefix_hits: dict[str, int] = {}
        self.request_prompt_tokens: dict[str, int] = {}
        self.requests: dict[str, RequestMeta] = {}
        self.request_hints: dict[str, KVFabricRequestHints] = {}
        self.request_defer_reasons: dict[str, str] = {}
        self.request_admission_limit_state: dict[str, tuple[int, int]] = {}
        self.family_index = PrefixFamilyIndex()
        self.hint_family_index = HintFamilyIndex()
        self._log_file: Any | None = None
        self._log_buffer: list[str] = []
        self._event_seq = 0
        self._emit(
            "tracker_initialized",
            policy=self.eviction_policy,
            log_path=str(self.log_path) if self.log_path else None,
            family_tree=self.enable_family_tree,
            request_meta=self.enable_request_meta,
            hints=self.enable_hints,
            hint_admission=self.hint_admission,
            hint_scheduler=self.hint_scheduler,
            hint_low_reuse_discovery_tokens=(
                self.hint_low_reuse_discovery_tokens
            ),
            hint_low_reuse_min_cache_blocks=(
                self.hint_low_reuse_min_cache_blocks
            ),
            hint_bypass_discovery_tokens=self.hint_bypass_discovery_tokens,
            hint_bypass_min_cache_blocks=self.hint_bypass_min_cache_blocks,
            hint_transient_discovery_tokens=(
                self.hint_transient_discovery_tokens
            ),
            hint_durable_discovery_tokens=(
                self.hint_durable_discovery_tokens
            ),
            hint_durable_min_hit_tokens=self.hint_durable_min_hit_tokens,
            scheduler_trace=self.scheduler_trace,
            admission_policy=self.admission_policy,
            log_buffer_size=self.log_buffer_size,
            admission_use_eviction_risk=self.admission_use_eviction_risk,
            admission_limit_cold_miss=self.admission_limit_cold_miss,
            admission_head_window=self.admission_head_window,
            admission_cold_discovery_blocks=self.admission_cold_discovery_blocks,
            admission_cold_discovery_tokens=self.admission_cold_discovery_tokens,
            scheduler_affinity=self.scheduler_affinity,
            scheduler_positive_scan_window=self.scheduler_positive_scan_window,
            scheduler_positive_min_risk_ratio=(
                self.scheduler_positive_min_risk_ratio
            ),
            scheduler_positive_score_margin=self.scheduler_positive_score_margin,
            scheduler_positive_max_per_step=self.scheduler_positive_max_per_step,
            scheduler_positive_hit_aware=self.scheduler_positive_hit_aware,
            scheduler_positive_hit_topk=self.scheduler_positive_hit_topk,
            scheduler_positive_hit_weight=self.scheduler_positive_hit_weight,
            scheduler_positive_hit_max_bonus=(
                self.scheduler_positive_hit_max_bonus
            ),
            scheduler_positive_session_turn_bonus=(
                self.scheduler_positive_session_turn_bonus
            ),
            scheduler_head_age_guard_ms=self.scheduler_head_age_guard_ms,
            scheduler_low_reuse_head_age_guard_ms=(
                self.scheduler_low_reuse_head_age_guard_ms
            ),
            scheduler_latency_protected_classes=(
                list(self.scheduler_latency_protected_classes)
            ),
            scheduler_latency_protected_min_output_tokens=(
                self.scheduler_latency_protected_min_output_tokens
            ),
            scheduler_latency_protected_head_guard_ms=(
                self.scheduler_latency_protected_head_guard_ms
            ),
            scheduler_latency_protected_promote_age_ms=(
                self.scheduler_latency_protected_promote_age_ms
            ),
            scheduler_latency_protected_min_risk_ratio=(
                self.scheduler_latency_protected_min_risk_ratio
            ),
            scheduler_defer_max_count=self.scheduler_defer_max_count,
            scheduler_defer_low_reuse_max_count=(
                self.scheduler_defer_low_reuse_max_count
            ),
            scheduler_defer_max_age_ms=self.scheduler_defer_max_age_ms,
            scheduler_defer_low_reuse_max_age_ms=(
                self.scheduler_defer_low_reuse_max_age_ms
            ),
        )

    @classmethod
    def from_env(cls) -> "KVFabricLifecycleTracker | None":
        if not _env_enabled("KVFABRIC_LIFECYCLE"):
            return None
        return cls(
            enabled=True,
            log_path=os.environ.get("KVFABRIC_LIFECYCLE_LOG_PATH"),
        )

    def _emit(self, event: str, **payload: Any) -> None:
        if not self.enabled:
            return

        self._event_seq += 1
        record = {
            "seq": self._event_seq,
            "event": event,
            "time_ns": time.monotonic_ns(),
            **payload,
        }
        if self.log_path is None:
            return

        line = json.dumps(record, sort_keys=True) + "\n"
        if self.log_buffer_size <= 1:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line)
            return

        self._log_buffer.append(line)
        if len(self._log_buffer) >= self.log_buffer_size:
            self._flush_events()

    def _flush_events(self) -> None:
        if self.log_path is None or not self._log_buffer:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self._log_file is None:
            self._log_file = self.log_path.open("a", encoding="utf-8")
        self._log_file.writelines(self._log_buffer)
        self._log_file.flush()
        self._log_buffer.clear()

    def close(self) -> None:
        self._flush_events()
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _get_or_create(self, block: "KVCacheBlock") -> LifecycleBlockMeta:
        now_ns = time.monotonic_ns()
        meta = self.blocks.get(block.block_id)
        if meta is None:
            meta = LifecycleBlockMeta(
                block_id=block.block_id,
                ref_count=block.ref_cnt,
                created_time_ns=now_ns,
                last_access_time_ns=now_ns,
            )
            self.blocks[block.block_id] = meta
        return meta

    def _refresh_family_fields(self, meta: LifecycleBlockMeta) -> None:
        if not self.enable_family_tree or meta.block_hash is None:
            return
        payload = self.family_index.event_payload(meta.block_hash)
        meta.family_id = payload["family_id"]  # type: ignore[assignment]
        meta.root_hash = payload["root_hash"]  # type: ignore[assignment]
        meta.parent_hash = payload["parent_hash"]  # type: ignore[assignment]
        meta.family_hit_count = int(payload["family_hit_count"] or 0)
        meta.family_branch_count = int(payload["family_branch_count"] or 0)
        meta.family_regret_count = int(payload["family_regret_count"] or 0)
        meta.protected_depth = max(
            int(payload["protected_depth"] or 0),
            self.protected_depth_floor if meta.family_hit_count > 0 else 0,
        )
        meta.branch_factor = max(meta.branch_factor, meta.family_branch_count)

    def _pressure_state(self, free_blocks: int, total_blocks: int) -> tuple[str, float]:
        if total_blocks <= 0:
            return "UNKNOWN", 1.0
        free_ratio = free_blocks / total_blocks
        if free_ratio <= self.pressure_red_ratio:
            return "RED", free_ratio
        if free_ratio <= self.pressure_orange_ratio:
            return "ORANGE", free_ratio
        if free_ratio <= self.pressure_yellow_ratio:
            return "YELLOW", free_ratio
        return "GREEN", free_ratio

    @staticmethod
    def _pressure_rank(state: str) -> int:
        return {
            "UNKNOWN": 0,
            "GREEN": 1,
            "YELLOW": 2,
            "ORANGE": 3,
            "RED": 4,
        }.get(state, 0)

    def _max_pressure_state(self, *states: str) -> str:
        return max(states, key=self._pressure_rank)

    def _risk_pressure_state(self, eviction_risk_ratio: float) -> str:
        if not self.admission_use_eviction_risk:
            return "GREEN"
        if eviction_risk_ratio >= self.admission_risk_red_ratio:
            return "RED"
        if eviction_risk_ratio >= self.admission_risk_orange_ratio:
            return "ORANGE"
        if eviction_risk_ratio >= self.admission_risk_yellow_ratio:
            return "YELLOW"
        return "GREEN"

    def _classify_request(self, prompt_tokens: int, hit_tokens: int) -> str:
        if hit_tokens > 0:
            if prompt_tokens >= self.admission_min_prompt_tokens:
                return "long_reuse"
            return "short_reuse"
        if prompt_tokens >= self.admission_min_prompt_tokens:
            return "cold_long"
        return "cold_short"

    def _get_or_create_request(
        self,
        request_id: str,
        now_ns: int | None = None,
    ) -> RequestMeta:
        now_ns = now_ns or time.monotonic_ns()
        meta = self.requests.get(request_id)
        if meta is None:
            meta = RequestMeta(
                request_id=request_id,
                arrival_time_ns=now_ns,
                last_update_time_ns=now_ns,
            )
            self.requests[request_id] = meta
        return meta

    @staticmethod
    def _apply_hints_to_request_meta(
        request_meta: RequestMeta,
        hints: KVFabricRequestHints,
    ) -> None:
        request_meta.hint_request_class = hints.request_class
        request_meta.hint_tenant_id = hints.tenant_id
        request_meta.hint_family_id = hints.family_id
        request_meta.hint_family_key = hints.family_key
        request_meta.hint_cache_priority = hints.cache_priority
        request_meta.hint_expected_reuse = hints.expected_reuse
        request_meta.hint_phase = hints.phase
        request_meta.hint_burst = hints.burst
        request_meta.hint_session_id = hints.session_id
        request_meta.hint_turn_index = hints.turn_index
        request_meta.hint_slo_ms = hints.slo_ms
        request_meta.hint_confidence = hints.hint_confidence
        request_meta.hint_has_hints = hints.has_hints

    def _get_request_hints(
        self,
        request_id: str,
    ) -> KVFabricRequestHints | None:
        return self.request_hints.get(request_id)

    def _hint_event_fields(self, request_id: str) -> dict[str, object]:
        hints = self._get_request_hints(request_id)
        if hints is None:
            return KVFabricRequestHints().event_fields()
        return hints.event_fields()

    def on_request_hints(
        self,
        request_id: str,
        trace_headers: Any,
        prompt_tokens: int = 0,
    ) -> None:
        if not self.enabled or not self.enable_hints:
            return
        if request_id in self.request_hints:
            return

        hints = KVFabricRequestHints.from_headers(trace_headers)
        now_ns = time.monotonic_ns()
        self.request_hints[request_id] = hints
        request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
        if prompt_tokens > 0:
            request_meta.prompt_tokens = prompt_tokens
            self.request_prompt_tokens[request_id] = prompt_tokens
        request_meta.last_update_time_ns = now_ns
        self._apply_hints_to_request_meta(request_meta, hints)

        runtime = self.hint_family_index.observe_request(
            hints,
            prompt_tokens=prompt_tokens,
            now_ns=now_ns,
        )
        if hints.has_hints:
            payload = {
                "request_id": request_id,
                "prompt_tokens": prompt_tokens,
                **hints.event_fields(),
            }
            if runtime is not None:
                payload.update(runtime.event_fields())
            self._emit("request_hints_observed", **payload)

    def _discovery_blocks_from_tokens(
        self,
        token_budget: int,
        block_size: int,
        min_blocks: int,
    ) -> int:
        block_size = max(block_size, 1)
        return max(min_blocks, (max(token_budget, 0) + block_size - 1) // block_size)

    def _hint_discovery_blocks(
        self,
        hints: KVFabricRequestHints | None,
        request_hit_tokens: int,
        pressure_state: str,
        block_size: int,
        default_discovery_blocks: int,
    ) -> tuple[int, str]:
        if (
            not self.enable_hints
            or not self.hint_admission
            or hints is None
            or not hints.has_hints
        ):
            return default_discovery_blocks, "default"

        if hints.is_durable:
            if request_hit_tokens >= self.hint_durable_min_hit_tokens:
                return default_discovery_blocks, "hint_durable_reuse"
            durable_blocks = self._discovery_blocks_from_tokens(
                self.hint_durable_discovery_tokens,
                block_size,
                self.admission_anchor_blocks,
            )
            if pressure_state in {"RED"}:
                durable_blocks = min(durable_blocks, default_discovery_blocks)
            else:
                durable_blocks = max(durable_blocks, default_discovery_blocks)
            return durable_blocks, "hint_durable_warmup"

        if hints.cache_priority == "bypass":
            low_blocks = self._discovery_blocks_from_tokens(
                self.hint_bypass_discovery_tokens,
                block_size,
                self.hint_bypass_min_cache_blocks,
            )
            return min(default_discovery_blocks, low_blocks), "hint_bypass"

        if hints.is_low_reuse:
            low_blocks = self._discovery_blocks_from_tokens(
                self.hint_low_reuse_discovery_tokens,
                block_size,
                self.hint_low_reuse_min_cache_blocks,
            )
            return min(default_discovery_blocks, low_blocks), "hint_low_reuse"

        if hints.is_transient:
            transient_blocks = self._discovery_blocks_from_tokens(
                self.hint_transient_discovery_tokens,
                block_size,
                self.admission_anchor_blocks,
            )
            return min(default_discovery_blocks, transient_blocks), "hint_transient"

        return default_discovery_blocks, "hint_unknown"

    def _hint_should_protect_from_defer(
        self,
        hints: KVFabricRequestHints | None,
    ) -> bool:
        if (
            not self.enable_hints
            or not self.hint_scheduler
            or hints is None
            or not hints.has_hints
        ):
            return False
        return hints.is_durable

    def _hint_defer_reason(
        self,
        hints: KVFabricRequestHints | None,
        request_class: str,
    ) -> tuple[str, float]:
        threshold = self.scheduler_defer_min_risk_ratio
        if (
            not self.enable_hints
            or not self.hint_scheduler
            or hints is None
            or not hints.has_hints
        ):
            return request_class, threshold
        if hints.cache_priority == "bypass":
            return "hint_bypass_cold_miss", max(
                0.0,
                threshold - self.hint_defer_low_reuse_risk_delta,
            )
        if hints.is_low_reuse:
            return "hint_low_reuse_cold_miss", max(
                0.0,
                threshold - self.hint_defer_low_reuse_risk_delta,
            )
        if hints.is_transient:
            return "hint_transient_cold_miss", threshold
        return f"hint_{hints.request_class}_cold_miss", threshold

    def _is_latency_protected_request(
        self,
        hints: KVFabricRequestHints | None,
        max_output_tokens: int = 0,
    ) -> bool:
        if (
            not self.scheduler_latency_protected_classes
            or hints is None
            or not hints.has_hints
        ):
            return False
        if (
            self.scheduler_latency_protected_min_output_tokens > 0
            and max_output_tokens
            < self.scheduler_latency_protected_min_output_tokens
        ):
            return False

        request_class = hints.request_class
        for token in self.scheduler_latency_protected_classes:
            if token == "low_reuse_long" and hints.is_low_reuse:
                return True
            if token == "long_output":
                return True
            if token and token in request_class:
                return True
        return False

    @staticmethod
    def _request_age_ms(
        request_meta: RequestMeta,
        now_ns: int,
        arrival_time: float = 0.0,
    ) -> float:
        now_wall = time.time()
        if arrival_time > 0 and now_wall >= arrival_time:
            return (now_wall - arrival_time) * 1000.0
        if request_meta.arrival_time_ns:
            return (now_ns - request_meta.arrival_time_ns) / 1_000_000.0
        return 0.0

    def _emit_defer_skipped(
        self,
        request_id: str,
        prompt_tokens: int,
        hit_tokens: int,
        waiting_queue_size: int,
        token_budget: int,
        eviction_risk_ratio: float,
        defer_reason: str,
        skip_reason: str,
        threshold: float,
        request_age_ms: float,
        deferred_count: int,
    ) -> None:
        if not self.scheduler_trace:
            return
        hints = self._get_request_hints(request_id)
        runtime = self.hint_family_index.get(hints)
        payload = {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "hit_tokens": hit_tokens,
            "waiting_queue_size": waiting_queue_size,
            "token_budget": token_budget,
            "eviction_risk_ratio": eviction_risk_ratio,
            "scheduler_affinity": self.scheduler_affinity,
            "defer_reason": defer_reason,
            "skip_reason": skip_reason,
            "defer_threshold": threshold,
            "request_age_ms": request_age_ms,
            "deferred_count": deferred_count,
            "scheduler_defer_max_count": self.scheduler_defer_max_count,
            "scheduler_defer_low_reuse_max_count": (
                self.scheduler_defer_low_reuse_max_count
            ),
            "scheduler_defer_max_age_ms": self.scheduler_defer_max_age_ms,
            "scheduler_defer_low_reuse_max_age_ms": (
                self.scheduler_defer_low_reuse_max_age_ms
            ),
            **self._hint_event_fields(request_id),
        }
        if runtime is not None:
            payload.update(runtime.event_fields())
        self._emit("request_defer_skipped", **payload)

    def on_block_allocated(self, block: "KVCacheBlock") -> None:
        if not self.enabled or block.is_null:
            return
        now_ns = time.monotonic_ns()
        meta = self._get_or_create(block)
        meta.ref_count = block.ref_cnt
        meta.state = "ACTIVE"
        meta.last_access_time_ns = now_ns
        self._emit("block_allocated", **asdict(meta))

    def on_block_sealed(
        self,
        block: "KVCacheBlock",
        prefix_depth: int,
        block_size: int,
        parent_hash: "BlockHashWithGroupId | None" = None,
        root_hash: "BlockHashWithGroupId | None" = None,
        request_id: str | None = None,
    ) -> None:
        if not self.enabled or block.is_null:
            return

        now_ns = time.monotonic_ns()
        block_hash = _hash_to_hex(block.block_hash)
        parent_hash_hex = _hash_to_hex(parent_hash)
        root_hash_hex = _hash_to_hex(root_hash)
        meta = self._get_or_create(block)
        meta.block_hash = block_hash
        meta.prefix_depth = max(meta.prefix_depth, prefix_depth)
        meta.recompute_cost_tokens = max(
            meta.recompute_cost_tokens, prefix_depth * block_size
        )
        meta.ref_count = block.ref_cnt
        meta.share_degree = max(meta.share_degree, block.ref_cnt)
        meta.state = "SHARED" if block.ref_cnt > 1 else "SEALED"
        meta.last_access_time_ns = now_ns

        rebuilt_from_eviction = False
        rebuild_gap_seconds = 0.0
        if block_hash is not None:
            shadow = self.evicted_shadows.pop(block_hash, None)
            if shadow is not None:
                rebuilt_from_eviction = True
                rebuild_gap_seconds = (now_ns - shadow.evicted_time_ns) / 1e9

        if self.enable_family_tree and block_hash is not None:
            node, family = self.family_index.observe_block(
                block_hash=block_hash,
                parent_hash=parent_hash_hex,
                root_hash=root_hash_hex,
                depth=prefix_depth,
                rebuilt_from_eviction=rebuilt_from_eviction,
                now_ns=now_ns,
            )
            meta.family_id = family.family_id
            meta.root_hash = node.root_hash
            meta.parent_hash = node.parent_hash
            meta.family_hit_count = family.hit_count
            meta.family_branch_count = node.branch_count
            meta.family_regret_count = family.regret_count
            meta.protected_depth = max(
                family.protected_depth,
                self.protected_depth_floor if family.hit_count > 0 else 0,
            )
            meta.branch_factor = max(meta.branch_factor, node.branch_count)
            if request_id is not None and self.enable_request_meta:
                request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
                request_meta.family_id = family.family_id
                request_meta.last_update_time_ns = now_ns

        self._refresh_family_fields(meta)

        self._emit(
            "block_sealed",
            request_id=request_id,
            rebuilt_from_eviction=rebuilt_from_eviction,
            rebuild_gap_seconds=rebuild_gap_seconds,
            retain_score=self._retain_score(meta),
            **asdict(meta),
        )

    def on_block_touched(
        self,
        block: "KVCacheBlock",
        from_free_queue: bool = False,
    ) -> None:
        if not self.enabled or block.is_null:
            return

        meta = self._get_or_create(block)
        meta.block_hash = meta.block_hash or _hash_to_hex(block.block_hash)
        meta.ref_count = block.ref_cnt
        meta.hit_count += 1
        meta.share_degree = max(meta.share_degree, block.ref_cnt)
        if self.enable_family_tree and meta.block_hash is not None:
            self.family_index.touch(meta.block_hash, now_ns=time.monotonic_ns())
            self._refresh_family_fields(meta)
        meta.branch_factor = max(
            meta.branch_factor,
            meta.share_degree - 1,
            meta.family_branch_count,
        )
        meta.state = "SHARED" if block.ref_cnt > 1 else "ACTIVE"
        meta.last_access_time_ns = time.monotonic_ns()
        self._emit(
            "block_touched",
            from_free_queue=from_free_queue,
            retain_score=self._retain_score(meta),
            **asdict(meta),
        )

    def on_ref_count_changed(self, block: "KVCacheBlock") -> None:
        if not self.enabled or block.is_null:
            return

        meta = self._get_or_create(block)
        meta.ref_count = block.ref_cnt
        meta.share_degree = max(meta.share_degree, block.ref_cnt)
        self._refresh_family_fields(meta)
        if block.ref_cnt == 0:
            if meta.hit_count > 0 or meta.share_degree > 1:
                meta.state = "COOLING_HOT"
            elif meta.prefix_depth > 0:
                meta.state = "COOLING_WARM"
            else:
                meta.state = "CANDIDATE"
        else:
            meta.state = "SHARED" if block.ref_cnt > 1 else "ACTIVE"
        self._emit(
            "ref_count_changed",
            retain_score=self._retain_score(meta),
            **asdict(meta),
        )

    def on_block_evicted(self, block: "KVCacheBlock") -> None:
        if not self.enabled or block.is_null:
            return

        meta = self.blocks.pop(block.block_id, None)
        if meta is None:
            meta = self._get_or_create(block)
        meta.block_hash = meta.block_hash or _hash_to_hex(block.block_hash)
        meta.ref_count = block.ref_cnt
        meta.state = "EVICTED"
        if self.enable_family_tree and meta.block_hash is not None:
            self.family_index.evict(meta.block_hash, now_ns=time.monotonic_ns())
            self._refresh_family_fields(meta)
        retain_score = self._retain_score(meta)

        if meta.block_hash is not None:
            self.evicted_shadows[meta.block_hash] = EvictedShadow(
                block_hash=meta.block_hash,
                block_id=meta.block_id,
                prefix_depth=meta.prefix_depth,
                hit_count=meta.hit_count,
                share_degree=meta.share_degree,
                branch_factor=meta.branch_factor,
                recompute_cost_tokens=meta.recompute_cost_tokens,
                retain_score=retain_score,
                evicted_time_ns=time.monotonic_ns(),
                family_id=meta.family_id,
                root_hash=meta.root_hash,
                parent_hash=meta.parent_hash,
            )

        self._emit(
            "block_evicted",
            policy=self.eviction_policy,
            retain_score=retain_score,
            **asdict(meta),
        )

    def on_prefix_lookup(
        self,
        request_id: str,
        prompt_tokens: int,
        hit_tokens: int,
        skipped: bool,
        max_cache_hit_length: int,
        block_size: int = 1,
    ) -> None:
        if not self.enabled:
            return
        now_ns = time.monotonic_ns()
        first_miss_depth = 0
        if block_size > 0:
            first_miss_depth = max(hit_tokens // block_size, 0)
        request_class = self._classify_request(prompt_tokens, hit_tokens)
        self.request_prefix_hits[request_id] = hit_tokens
        self.request_prompt_tokens[request_id] = prompt_tokens
        hints = self._get_request_hints(request_id)
        hint_runtime = self.hint_family_index.observe_lookup(
            hints,
            hit_tokens=hit_tokens,
            now_ns=now_ns,
        )
        if self.enable_request_meta:
            request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
            request_meta.prompt_tokens = prompt_tokens
            request_meta.prefix_hit_tokens = hit_tokens
            request_meta.first_miss_depth = first_miss_depth
            request_meta.max_cache_hit_length = max_cache_hit_length
            request_meta.request_class = request_class
            request_meta.last_update_time_ns = now_ns
            request_meta.state = "LOOKUP_SKIPPED" if skipped else "LOOKUP"
            if hints is not None:
                self._apply_hints_to_request_meta(request_meta, hints)
        payload = {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "hit_tokens": hit_tokens,
            "skipped": skipped,
            "max_cache_hit_length": max_cache_hit_length,
            "block_size": block_size,
            "first_miss_depth": first_miss_depth,
            "request_class": request_class,
            "hit": hit_tokens > 0,
            **self._hint_event_fields(request_id),
        }
        if hint_runtime is not None:
            payload.update(hint_runtime.event_fields())
        self._emit(
            "prefix_lookup",
            **payload,
        )

    def use_kvfabric_eviction(self) -> bool:
        return self.enabled and self.eviction_policy in {
            "shared_aware",
            "family_protect",
        }

    def eviction_candidate_window(self, num_blocks: int, free_blocks: int) -> int:
        window = max(
            num_blocks * self.eviction_candidate_window_multiplier,
            self.eviction_candidate_window_min,
            num_blocks,
        )
        if self.eviction_candidate_window_max > 0:
            window = min(window, max(num_blocks, self.eviction_candidate_window_max))
        return min(window, free_blocks)

    def should_rank_lru_victims(self, victims: list["KVCacheBlock"]) -> bool:
        for block in victims:
            if block.block_hash is None:
                continue
            if self.is_protected(block):
                return True
            if self.eviction_rank_min_score > 0.0:
                if self.get_retain_score(block) >= self.eviction_rank_min_score:
                    return True
        return False

    def use_family_protect_eviction(self) -> bool:
        return self.enabled and self.eviction_policy == "family_protect"

    def limit_cache_blocks(
        self,
        request_id: str,
        num_cached_blocks: int,
        num_full_blocks: int,
        free_blocks: int,
        total_blocks: int,
        block_size: int = 1,
        head_window_blocks: int = 0,
        head_hashed_blocks: int = 0,
        head_protected_blocks: int = 0,
        eviction_risk_ratio: float = 0.0,
        protected_risk_ratio: float = 0.0,
    ) -> int:
        if self.admission_policy in {"off", "none", "disabled"} or total_blocks <= 0:
            return num_full_blocks
        if self.admission_policy == "auto" and self.eviction_policy == "lru":
            return num_full_blocks
        if self.admission_policy == "family_protect_only" and (
            self.eviction_policy != "family_protect"
        ):
            return num_full_blocks

        free_pressure_state, free_ratio = self._pressure_state(
            free_blocks, total_blocks
        )
        risk_pressure_state = self._risk_pressure_state(eviction_risk_ratio)
        pressure_state = self._max_pressure_state(
            free_pressure_state, risk_pressure_state
        )
        request_hit_tokens = self.request_prefix_hits.get(request_id, 0)
        request_prompt_tokens = self.request_prompt_tokens.get(request_id, 0)
        request_meta = self.requests.get(request_id)
        request_class = (
            request_meta.request_class
            if request_meta is not None
            else self._classify_request(request_prompt_tokens, request_hit_tokens)
        )
        hints = self._get_request_hints(request_id)
        if request_meta is not None and hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)
        if request_prompt_tokens < self.admission_min_prompt_tokens:
            return num_full_blocks
        cold_long_miss = request_hit_tokens <= 0
        force_cold_miss_cap = self.admission_limit_cold_miss and cold_long_miss
        if (
            self.enable_hints
            and self.hint_admission
            and hints is not None
            and hints.has_hints
        ):
            if hints.is_durable:
                force_cold_miss_cap = False
            elif hints.is_low_reuse:
                force_cold_miss_cap = force_cold_miss_cap or cold_long_miss
        if pressure_state == "GREEN" and not force_cold_miss_cap:
            return num_full_blocks
        if (
            hints is not None
            and hints.has_hints
            and hints.is_durable
            and request_hit_tokens >= self.hint_durable_min_hit_tokens
        ):
            return num_full_blocks
        if request_hit_tokens >= self.admission_reuse_min_hit_tokens:
            return num_full_blocks
        if (
            hints is not None
            and hints.has_hints
            and hints.is_durable
            and pressure_state != "RED"
        ):
            return num_full_blocks
        if (
            request_class in {"long_reuse", "short_reuse"}
            and pressure_state == "YELLOW"
        ):
            return num_full_blocks

        anchor_blocks = max(1, self.admission_anchor_blocks)
        if self.admission_cold_discovery_blocks > 0:
            discovery_blocks = self.admission_cold_discovery_blocks
        else:
            discovery_blocks = (
                self.admission_cold_discovery_tokens + max(block_size, 1) - 1
            ) // max(block_size, 1)
        discovery_blocks = max(anchor_blocks, discovery_blocks)
        discovery_blocks, admission_reason = self._hint_discovery_blocks(
            hints,
            request_hit_tokens=request_hit_tokens,
            pressure_state=pressure_state,
            block_size=block_size,
            default_discovery_blocks=discovery_blocks,
        )
        if request_hit_tokens <= 0:
            anchor_blocks = discovery_blocks
            allow_zero_cache = (
                admission_reason in {"hint_bypass", "hint_low_reuse"}
                and discovery_blocks <= 0
            )
            if pressure_state == "RED" and not allow_zero_cache:
                anchor_blocks = max(
                    self.admission_anchor_blocks,
                    min(discovery_blocks, 32),
                )
        elif pressure_state == "YELLOW":
            anchor_blocks = max(anchor_blocks, num_cached_blocks + 1)
        limited = min(
            num_full_blocks,
            max(num_cached_blocks, anchor_blocks),
        )
        if limited < num_full_blocks:
            limit_state = (num_full_blocks, limited)
            previous_limit_state = self.request_admission_limit_state.get(request_id)
            self.request_admission_limit_state[request_id] = limit_state
            if previous_limit_state == limit_state:
                return limited

            now_ns = time.monotonic_ns()
            if request_meta is not None:
                request_meta.admission_limited_count += 1
            hint_runtime = self.hint_family_index.observe_admission_limit(
                hints,
                now_ns=now_ns,
            )
            payload = {
                "request_id": request_id,
                "request_hit_tokens": request_hit_tokens,
                "request_prompt_tokens": request_prompt_tokens,
                "num_cached_blocks": num_cached_blocks,
                "original_full_blocks": num_full_blocks,
                "limited_full_blocks": limited,
                "free_blocks": free_blocks,
                "total_blocks": total_blocks,
                "free_ratio": free_ratio,
                "free_pressure_state": free_pressure_state,
                "risk_pressure_state": risk_pressure_state,
                "pressure_state": pressure_state,
                "head_window_blocks": head_window_blocks,
                "head_hashed_blocks": head_hashed_blocks,
                "head_protected_blocks": head_protected_blocks,
                "eviction_risk_ratio": eviction_risk_ratio,
                "protected_risk_ratio": protected_risk_ratio,
                "block_size": block_size,
                "request_class": request_class,
                "admission_reason": admission_reason,
                "admission_policy": self.admission_policy,
                "admission_limit_cold_miss": self.admission_limit_cold_miss,
                "admission_cold_discovery_blocks": (
                    self.admission_cold_discovery_blocks
                ),
                "admission_cold_discovery_tokens": (
                    self.admission_cold_discovery_tokens
                ),
                "hint_low_reuse_discovery_tokens": (
                    self.hint_low_reuse_discovery_tokens
                ),
                "hint_low_reuse_min_cache_blocks": (
                    self.hint_low_reuse_min_cache_blocks
                ),
                "hint_bypass_discovery_tokens": (
                    self.hint_bypass_discovery_tokens
                ),
                "hint_bypass_min_cache_blocks": (
                    self.hint_bypass_min_cache_blocks
                ),
                **self._hint_event_fields(request_id),
            }
            if hint_runtime is not None:
                payload.update(hint_runtime.event_fields())
            self._emit("cache_admission_limited", **payload)
        return limited

    def should_defer_request(
        self,
        request_id: str,
        prompt_tokens: int,
        hit_tokens: int,
        max_output_tokens: int,
        waiting_queue_size: int,
        token_budget: int,
        already_deferred: bool,
        deferrals_this_step: int,
        eviction_risk_ratio: float,
    ) -> bool:
        if self.scheduler_affinity in {"0", "off", "none", "disabled"}:
            return False
        if self.eviction_policy == "lru":
            return False
        if already_deferred:
            return False
        if deferrals_this_step >= self.scheduler_defer_max_per_step:
            return False
        if waiting_queue_size < self.scheduler_defer_min_waiting:
            return False
        if prompt_tokens < self.scheduler_defer_min_prompt_tokens:
            return False
        if hit_tokens > 0:
            return False
        if token_budget <= 0:
            return False

        now_ns = time.monotonic_ns()
        request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
        request_meta.prompt_tokens = max(request_meta.prompt_tokens, prompt_tokens)
        request_meta.max_output_tokens = max(
            request_meta.max_output_tokens,
            max_output_tokens,
        )
        request_meta.last_update_time_ns = now_ns
        request_class = request_meta.request_class
        if request_class == "unknown":
            request_class = self._classify_request(prompt_tokens, hit_tokens)
            request_meta.request_class = request_class
        hints = self._get_request_hints(request_id)
        if hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)
        if self._hint_should_protect_from_defer(hints):
            self.request_defer_reasons.pop(request_id, None)
            return False

        reason, threshold = self._hint_defer_reason(hints, request_class)
        request_age_ms = self._request_age_ms(request_meta, now_ns)
        if self._is_latency_protected_request(hints, max_output_tokens):
            self.request_defer_reasons.pop(request_id, None)
            self._emit_defer_skipped(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hit_tokens=hit_tokens,
                waiting_queue_size=waiting_queue_size,
                token_budget=token_budget,
                eviction_risk_ratio=eviction_risk_ratio,
                defer_reason=reason,
                skip_reason="latency_protected_defer_bypass",
                threshold=threshold,
                request_age_ms=request_age_ms,
                deferred_count=request_meta.deferred_count,
            )
            return False

        should_defer = eviction_risk_ratio >= threshold
        if not should_defer:
            self.request_defer_reasons.pop(request_id, None)
            return False

        deferred_count = request_meta.deferred_count
        low_reuse = bool(
            hints is not None and hints.has_hints and hints.is_low_reuse
        )
        if (
            low_reuse
            and self.scheduler_defer_low_reuse_max_count > 0
            and deferred_count >= self.scheduler_defer_low_reuse_max_count
        ):
            self.request_defer_reasons.pop(request_id, None)
            self._emit_defer_skipped(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hit_tokens=hit_tokens,
                waiting_queue_size=waiting_queue_size,
                token_budget=token_budget,
                eviction_risk_ratio=eviction_risk_ratio,
                defer_reason=reason,
                skip_reason="low_reuse_defer_count_cap",
                threshold=threshold,
                request_age_ms=request_age_ms,
                deferred_count=deferred_count,
            )
            return False
        if (
            low_reuse
            and self.scheduler_defer_low_reuse_max_age_ms > 0
            and request_age_ms >= self.scheduler_defer_low_reuse_max_age_ms
        ):
            self.request_defer_reasons.pop(request_id, None)
            self._emit_defer_skipped(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hit_tokens=hit_tokens,
                waiting_queue_size=waiting_queue_size,
                token_budget=token_budget,
                eviction_risk_ratio=eviction_risk_ratio,
                defer_reason=reason,
                skip_reason="low_reuse_defer_age_cap",
                threshold=threshold,
                request_age_ms=request_age_ms,
                deferred_count=deferred_count,
            )
            return False
        if (
            self.scheduler_defer_max_count > 0
            and deferred_count >= self.scheduler_defer_max_count
        ):
            self.request_defer_reasons.pop(request_id, None)
            self._emit_defer_skipped(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hit_tokens=hit_tokens,
                waiting_queue_size=waiting_queue_size,
                token_budget=token_budget,
                eviction_risk_ratio=eviction_risk_ratio,
                defer_reason=reason,
                skip_reason="defer_count_cap",
                threshold=threshold,
                request_age_ms=request_age_ms,
                deferred_count=deferred_count,
            )
            return False
        if (
            self.scheduler_defer_max_age_ms > 0
            and request_age_ms >= self.scheduler_defer_max_age_ms
        ):
            self.request_defer_reasons.pop(request_id, None)
            self._emit_defer_skipped(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hit_tokens=hit_tokens,
                waiting_queue_size=waiting_queue_size,
                token_budget=token_budget,
                eviction_risk_ratio=eviction_risk_ratio,
                defer_reason=reason,
                skip_reason="defer_age_cap",
                threshold=threshold,
                request_age_ms=request_age_ms,
                deferred_count=deferred_count,
            )
            return False

        self.request_defer_reasons[request_id] = reason
        return True

    def should_scan_positive_requests(
        self,
        waiting_queue_size: int,
        promotions_this_step: int,
        eviction_risk_ratio: float,
    ) -> bool:
        if self.scheduler_affinity not in {"positive", "hybrid"}:
            return False
        if self.eviction_policy == "lru":
            return False
        if not self.enable_hints or not self.hint_scheduler:
            return False
        if self.scheduler_positive_scan_window <= 1:
            return False
        if waiting_queue_size < self.scheduler_defer_min_waiting:
            return False
        if promotions_this_step >= self.scheduler_positive_max_per_step:
            return False
        return eviction_risk_ratio >= self.scheduler_positive_min_risk_ratio

    def should_scan_latency_protected_requests(
        self,
        waiting_queue_size: int,
        promotions_this_step: int,
        eviction_risk_ratio: float,
    ) -> bool:
        if not self.scheduler_latency_protected_classes:
            return False
        if self.scheduler_latency_protected_promote_age_ms <= 0:
            return False
        if self.scheduler_affinity not in {"positive", "hybrid"}:
            return False
        if self.eviction_policy == "lru":
            return False
        if not self.enable_hints or not self.hint_scheduler:
            return False
        if self.scheduler_positive_scan_window <= 1:
            return False
        if waiting_queue_size < self.scheduler_defer_min_waiting:
            return False
        if promotions_this_step >= self.scheduler_positive_max_per_step:
            return False
        return eviction_risk_ratio >= self.scheduler_latency_protected_min_risk_ratio

    def should_promote_latency_protected_request(
        self,
        request_id: str,
        prompt_tokens: int,
        max_output_tokens: int,
        arrival_time: float,
        queue_index: int,
    ) -> tuple[bool, float]:
        if queue_index <= 0:
            return False, 0.0
        now_ns = time.monotonic_ns()
        request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
        request_meta.prompt_tokens = max(request_meta.prompt_tokens, prompt_tokens)
        request_meta.max_output_tokens = max(
            request_meta.max_output_tokens,
            max_output_tokens,
        )
        request_meta.last_update_time_ns = now_ns
        hints = self._get_request_hints(request_id)
        if hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)
        if not self._is_latency_protected_request(hints, max_output_tokens):
            return False, 0.0
        request_age_ms = self._request_age_ms(
            request_meta,
            now_ns,
            arrival_time=arrival_time,
        )
        return (
            request_age_ms >= self.scheduler_latency_protected_promote_age_ms,
            request_age_ms,
        )

    def positive_request_score(
        self,
        request_id: str,
        prompt_tokens: int,
        queue_index: int,
        estimated_hit_tokens: int = 0,
        max_output_tokens: int = 0,
    ) -> float:
        hints = self._get_request_hints(request_id)
        if hints is None or not hints.has_hints:
            return 0.0

        score = max(0.0, 1.0 - 0.02 * queue_index)
        confidence = max(min(hints.hint_confidence, 1.0), 0.0)
        if hints.is_durable:
            score += 12.0 * confidence
        if hints.cache_priority == "high":
            score += 8.0 * confidence
        if hints.expected_reuse == "durable":
            score += 6.0 * confidence
        if hints.is_transient:
            score += 2.0 * confidence
        if hints.turn_index > 0:
            score += min(hints.turn_index, 16) * 0.5 * confidence
        if hints.session_id and hints.turn_index > 0 and hints.is_durable:
            score += self.scheduler_positive_session_turn_bonus * confidence
        if prompt_tokens >= self.scheduler_defer_min_prompt_tokens and hints.is_durable:
            score += min(prompt_tokens / 1024.0, 6.0)

        runtime = self.hint_family_index.get(hints)
        if runtime is not None:
            score += min(runtime.request_count, 32) * 0.15
            score += min(runtime.scheduled_count, 32) * 0.10
            score += min(runtime.prefix_hit_tokens / 512.0, 16.0)
            score -= min(runtime.deferred_count, 16) * 0.05

        request_class = hints.request_class
        if hints.cache_priority == "bypass":
            score -= 24.0
        elif hints.is_low_reuse:
            score -= 14.0
        if "cold" in request_class or "unique" in request_class:
            score -= 8.0
        if "decode" in request_class:
            score -= 4.0
        if self._is_latency_protected_request(hints, max_output_tokens):
            score -= 6.0
        score += self.positive_hit_bonus(estimated_hit_tokens)
        return score

    def positive_hit_bonus(self, estimated_hit_tokens: int) -> float:
        if estimated_hit_tokens <= 0:
            return 0.0
        return min(
            estimated_hit_tokens * self.scheduler_positive_hit_weight,
            self.scheduler_positive_hit_max_bonus,
        )

    def should_promote_positive_request(
        self,
        best_score: float,
        head_score: float,
    ) -> bool:
        return best_score >= max(1.0, head_score + self.scheduler_positive_score_margin)

    def should_guard_positive_promotion(
        self,
        head_request_id: str,
        head_prompt_tokens: int,
        head_max_output_tokens: int,
        head_arrival_time: float,
        best_request_id: str,
        best_score: float,
        head_score: float,
        waiting_queue_size: int,
        eviction_risk_ratio: float,
    ) -> bool:
        if (
            self.scheduler_head_age_guard_ms <= 0
            and self.scheduler_low_reuse_head_age_guard_ms <= 0
            and self.scheduler_latency_protected_head_guard_ms <= 0
        ):
            return False
        if head_request_id == best_request_id:
            return False

        now_ns = time.monotonic_ns()
        request_meta = self._get_or_create_request(head_request_id, now_ns=now_ns)
        request_meta.prompt_tokens = max(
            request_meta.prompt_tokens,
            head_prompt_tokens,
        )
        request_meta.max_output_tokens = max(
            request_meta.max_output_tokens,
            head_max_output_tokens,
        )
        request_meta.last_update_time_ns = now_ns
        hints = self._get_request_hints(head_request_id)
        if hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)

        head_age_ms = self._request_age_ms(
            request_meta,
            now_ns,
            arrival_time=head_arrival_time,
        )

        low_reuse = bool(
            hints is not None
            and hints.has_hints
            and (
                hints.is_low_reuse
                or hints.cache_priority in {"low", "bypass"}
                or hints.expected_reuse == "none"
            )
        )
        latency_protected = self._is_latency_protected_request(
            hints,
            head_max_output_tokens,
        )
        threshold_ms = self.scheduler_head_age_guard_ms
        skip_reason = "head_age_guard"
        if (
            latency_protected
            and self.scheduler_latency_protected_head_guard_ms > 0
        ):
            threshold_ms = self.scheduler_latency_protected_head_guard_ms
            skip_reason = "latency_protected_head_age_guard"
        elif low_reuse and self.scheduler_low_reuse_head_age_guard_ms > 0:
            threshold_ms = self.scheduler_low_reuse_head_age_guard_ms
            skip_reason = "low_reuse_head_age_guard"
        if threshold_ms <= 0 or head_age_ms < threshold_ms:
            return False

        if self.scheduler_trace:
            runtime = self.hint_family_index.get(hints)
            payload = {
                "request_id": head_request_id,
                "prompt_tokens": head_prompt_tokens,
                "best_request_id": best_request_id,
                "head_score": head_score,
                "best_score": best_score,
                "waiting_queue_size": waiting_queue_size,
                "eviction_risk_ratio": eviction_risk_ratio,
                "scheduler_affinity": self.scheduler_affinity,
                "skip_reason": skip_reason,
                "head_age_ms": head_age_ms,
                "head_age_guard_ms": self.scheduler_head_age_guard_ms,
                "low_reuse_head_age_guard_ms": (
                    self.scheduler_low_reuse_head_age_guard_ms
                ),
                "latency_protected": latency_protected,
                "head_max_output_tokens": head_max_output_tokens,
                "latency_protected_head_guard_ms": (
                    self.scheduler_latency_protected_head_guard_ms
                ),
                **self._hint_event_fields(head_request_id),
            }
            if runtime is not None:
                payload.update(runtime.event_fields())
            self._emit("request_promotion_skipped", **payload)
        return True

    def on_request_promoted(
        self,
        request_id: str,
        prompt_tokens: int,
        queue_index: int,
        selected_score: float,
        head_score: float,
        waiting_queue_size: int,
        eviction_risk_ratio: float,
        estimated_hit_tokens: int = 0,
        selected_base_score: float | None = None,
        selected_hit_bonus: float = 0.0,
        head_base_score: float | None = None,
        hit_aware: bool = False,
        hit_topk: int = 0,
    ) -> None:
        if not self.enabled or not self.scheduler_trace:
            return
        hints = self._get_request_hints(request_id)
        runtime = self.hint_family_index.get(hints)
        payload = {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "queue_index": queue_index,
            "selected_score": selected_score,
            "head_score": head_score,
            "selected_base_score": (
                selected_score if selected_base_score is None else selected_base_score
            ),
            "head_base_score": head_score if head_base_score is None else head_base_score,
            "selected_hit_bonus": selected_hit_bonus,
            "estimated_hit_tokens": estimated_hit_tokens,
            "hit_aware": hit_aware,
            "hit_topk": hit_topk,
            "waiting_queue_size": waiting_queue_size,
            "eviction_risk_ratio": eviction_risk_ratio,
            "scheduler_affinity": self.scheduler_affinity,
            **self._hint_event_fields(request_id),
        }
        if runtime is not None:
            payload.update(runtime.event_fields())
        self._emit("request_promoted", **payload)

    def on_request_latency_promoted(
        self,
        request_id: str,
        prompt_tokens: int,
        max_output_tokens: int,
        queue_index: int,
        request_age_ms: float,
        waiting_queue_size: int,
        eviction_risk_ratio: float,
    ) -> None:
        if not self.enabled or not self.scheduler_trace:
            return
        hints = self._get_request_hints(request_id)
        runtime = self.hint_family_index.get(hints)
        payload = {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "max_output_tokens": max_output_tokens,
            "queue_index": queue_index,
            "request_age_ms": request_age_ms,
            "waiting_queue_size": waiting_queue_size,
            "eviction_risk_ratio": eviction_risk_ratio,
            "scheduler_affinity": self.scheduler_affinity,
            "promote_reason": "latency_protected_age",
            "latency_protected_promote_age_ms": (
                self.scheduler_latency_protected_promote_age_ms
            ),
            "latency_protected_min_output_tokens": (
                self.scheduler_latency_protected_min_output_tokens
            ),
            **self._hint_event_fields(request_id),
        }
        if runtime is not None:
            payload.update(runtime.event_fields())
        self._emit("request_latency_promoted", **payload)

    def on_request_deferred(
        self,
        request_id: str,
        prompt_tokens: int,
        hit_tokens: int,
        waiting_queue_size: int,
        token_budget: int,
        eviction_risk_ratio: float,
        head_window_blocks: int,
        head_hashed_blocks: int,
    ) -> None:
        if not self.enabled or not self.scheduler_trace:
            return
        hints = self._get_request_hints(request_id)
        if request_id in self.requests:
            self.requests[request_id].deferred_count += 1
        hint_runtime = self.hint_family_index.observe_defer(
            hints,
            now_ns=time.monotonic_ns(),
        )
        payload = {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "hit_tokens": hit_tokens,
            "waiting_queue_size": waiting_queue_size,
            "token_budget": token_budget,
            "eviction_risk_ratio": eviction_risk_ratio,
            "head_window_blocks": head_window_blocks,
            "head_hashed_blocks": head_hashed_blocks,
            "scheduler_affinity": self.scheduler_affinity,
            "defer_reason": self.request_defer_reasons.get(
                request_id,
                "cold_miss_pressure",
            ),
            **self._hint_event_fields(request_id),
        }
        if hint_runtime is not None:
            payload.update(hint_runtime.event_fields())
        self._emit("request_deferred", **payload)

    def get_retain_score(self, block: "KVCacheBlock") -> float:
        meta = self.blocks.get(block.block_id)
        if meta is None:
            return 0.0
        return self._retain_score(meta)

    def _retain_score(self, meta: LifecycleBlockMeta) -> float:
        score = meta.retain_score(
            use_reuse=self.retain_use_reuse,
            use_prefix=self.retain_use_prefix,
            use_recompute=self.retain_use_recompute,
        )
        if self.retain_use_reuse:
            score += self.family_index.family_value(meta.block_hash)
            score += 3.0 * min(meta.family_hit_count, 32)
            score += 4.0 * min(meta.family_branch_count, 8)
            score += 8.0 * min(meta.family_regret_count, 16)
        if self.retain_use_prefix and meta.protected_depth > 0:
            score += 2.0 * max(meta.protected_depth - meta.prefix_depth + 1, 0)
        return score

    def is_protected(self, block: "KVCacheBlock") -> bool:
        meta = self.blocks.get(block.block_id)
        if meta is None:
            return False
        self._refresh_family_fields(meta)
        return (
            meta.hit_count >= self.protect_min_hit_count
            or meta.share_degree >= self.protect_min_share_degree
            or meta.branch_factor >= self.protect_min_branch_factor
            or meta.family_hit_count >= self.protect_min_family_hits
            or meta.family_branch_count >= self.protect_min_family_branches
            or meta.family_regret_count > 0
            or (
                meta.protected_depth > 0
                and meta.prefix_depth > 0
                and meta.prefix_depth <= meta.protected_depth
            )
        )

    def _rank_key(
        self,
        indexed_block: tuple[int, "KVCacheBlock"],
    ) -> tuple[int, float, int]:
        original_index, block = indexed_block
        if block.block_hash is None:
            return 0, 0.0, original_index

        if self.eviction_policy == "family_protect":
            # Hard partition: first evict unprotected cached blocks. Protected
            # blocks are only considered if the unprotected pool cannot satisfy
            # the allocation.
            bucket = 2 if self.is_protected(block) else 1
        else:
            bucket = 1

        return bucket, self.get_retain_score(block), original_index

    def rank_eviction_candidates(
        self,
        candidates: list["KVCacheBlock"],
        num_blocks: int,
    ) -> list["KVCacheBlock"]:
        """Rank free-list candidates from cheapest to most valuable to evict.

        Blocks without a hash are genuinely free and should be reused before
        evicting prefix-cache entries. Hashed blocks are ordered by increasing
        retain score, with the original free-list order acting as a stable
        tie-breaker.
        """
        ranked = nsmallest(
            num_blocks,
            enumerate(candidates),
            key=self._rank_key,
        )
        selected = [block for _, block in ranked]
        hashed_candidates = [block for block in candidates if block.block_hash is not None]
        protected_candidates = [
            block for block in hashed_candidates if self.is_protected(block)
        ]
        hashed_selected = [block for block in selected if block.block_hash is not None]
        protected_selected = [
            block for block in hashed_selected if self.is_protected(block)
        ]
        selected_scores = [self.get_retain_score(block) for block in selected]
        self._emit(
            "eviction_candidates_ranked",
            policy=self.eviction_policy,
            retain_use_reuse=self.retain_use_reuse,
            retain_use_prefix=self.retain_use_prefix,
            retain_use_recompute=self.retain_use_recompute,
            protect_min_hit_count=self.protect_min_hit_count,
            protect_min_share_degree=self.protect_min_share_degree,
            protect_min_branch_factor=self.protect_min_branch_factor,
            protect_min_family_hits=self.protect_min_family_hits,
            protect_min_family_branches=self.protect_min_family_branches,
            protected_depth_floor=self.protected_depth_floor,
            eviction_candidate_window_min=self.eviction_candidate_window_min,
            eviction_candidate_window_multiplier=(
                self.eviction_candidate_window_multiplier
            ),
            eviction_candidate_window_max=self.eviction_candidate_window_max,
            eviction_rank_min_score=self.eviction_rank_min_score,
            candidate_count=len(candidates),
            selected_count=len(selected),
            candidate_hashed_count=len(hashed_candidates),
            candidate_protected_count=len(protected_candidates),
            selected_hashed_count=len(hashed_selected),
            selected_protected_count=len(protected_selected),
            selected_avg_retain_score=(
                sum(selected_scores) / len(selected_scores) if selected_scores else 0.0
            ),
            candidates=[
                {
                    "block_id": block.block_id,
                    "has_hash": block.block_hash is not None,
                    "protected": self.is_protected(block),
                    "retain_score": self.get_retain_score(block),
                    "ref_count": block.ref_cnt,
                    "family_id": (
                        self.blocks.get(block.block_id).family_id
                        if self.blocks.get(block.block_id) is not None
                        else None
                    ),
                    "family_branch_count": (
                        self.blocks.get(block.block_id).family_branch_count
                        if self.blocks.get(block.block_id) is not None
                        else 0
                    ),
                    "family_regret_count": (
                        self.blocks.get(block.block_id).family_regret_count
                        if self.blocks.get(block.block_id) is not None
                        else 0
                    ),
                }
                for block in selected[:16]
            ],
        )
        return selected

    def select_family_protect_candidates(
        self,
        candidates: list["KVCacheBlock"],
        num_blocks: int,
    ) -> list["KVCacheBlock"]:
        """Select victims without sorting when only hot-family protection is needed.

        The common pressure case has very few protected blocks repeatedly
        appearing near the LRU head. A full retain-score ranking over the
        window is unnecessarily expensive there. This selector keeps the LRU
        order for ordinary blocks, skips protected blocks while enough
        alternatives exist, and falls back to protected blocks only if the
        window cannot satisfy the allocation.
        """
        selected: list["KVCacheBlock"] = []
        deferred: list["KVCacheBlock"] = []
        hashed_count = 0
        protected_count = 0
        selected_hashed_count = 0
        selected_protected_count = 0

        for block in candidates:
            has_hash = block.block_hash is not None
            protected = has_hash and self.is_protected(block)
            if has_hash:
                hashed_count += 1
            if protected:
                protected_count += 1
                deferred.append(block)
                continue

            selected.append(block)
            if has_hash:
                selected_hashed_count += 1
            if len(selected) >= num_blocks:
                break

        if len(selected) < num_blocks:
            for block in deferred:
                selected.append(block)
                selected_hashed_count += 1
                selected_protected_count += 1
                if len(selected) >= num_blocks:
                    break

        selected_scores = [self.get_retain_score(block) for block in selected]
        payload: dict[str, Any] = {
            "policy": self.eviction_policy,
            "selector": "family_protect_linear",
            "retain_use_reuse": self.retain_use_reuse,
            "retain_use_prefix": self.retain_use_prefix,
            "retain_use_recompute": self.retain_use_recompute,
            "protect_min_hit_count": self.protect_min_hit_count,
            "protect_min_share_degree": self.protect_min_share_degree,
            "protect_min_branch_factor": self.protect_min_branch_factor,
            "protect_min_family_hits": self.protect_min_family_hits,
            "protect_min_family_branches": self.protect_min_family_branches,
            "protected_depth_floor": self.protected_depth_floor,
            "eviction_candidate_window_min": self.eviction_candidate_window_min,
            "eviction_candidate_window_multiplier": (
                self.eviction_candidate_window_multiplier
            ),
            "eviction_candidate_window_max": self.eviction_candidate_window_max,
            "eviction_rank_min_score": self.eviction_rank_min_score,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "candidate_hashed_count": hashed_count,
            "candidate_protected_count": protected_count,
            "selected_hashed_count": selected_hashed_count,
            "selected_protected_count": selected_protected_count,
            "selected_avg_retain_score": (
                sum(selected_scores) / len(selected_scores) if selected_scores else 0.0
            ),
        }
        if self.rank_log_candidates:
            payload["candidates"] = [
                {
                    "block_id": block.block_id,
                    "has_hash": block.block_hash is not None,
                    "protected": self.is_protected(block),
                    "retain_score": self.get_retain_score(block),
                    "ref_count": block.ref_cnt,
                    "family_id": (
                        self.blocks.get(block.block_id).family_id
                        if self.blocks.get(block.block_id) is not None
                        else None
                    ),
                    "family_branch_count": (
                        self.blocks.get(block.block_id).family_branch_count
                        if self.blocks.get(block.block_id) is not None
                        else 0
                    ),
                    "family_regret_count": (
                        self.blocks.get(block.block_id).family_regret_count
                        if self.blocks.get(block.block_id) is not None
                        else 0
                    ),
                }
                for block in selected[:16]
            ]
        self._emit("eviction_candidates_ranked", **payload)
        return selected

    def on_request_finished(
        self,
        request_id: str,
        computed_tokens: int = 0,
        output_tokens: int = 0,
        status: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        now_ns = time.monotonic_ns()
        request_meta = self.requests.pop(request_id, None)
        hints = self.request_hints.pop(request_id, None)
        self.request_defer_reasons.pop(request_id, None)
        self.request_admission_limit_state.pop(request_id, None)
        if request_meta is None:
            request_meta = RequestMeta(
                request_id=request_id,
                prompt_tokens=self.request_prompt_tokens.get(request_id, 0),
                prefix_hit_tokens=self.request_prefix_hits.get(request_id, 0),
                arrival_time_ns=now_ns,
                last_update_time_ns=now_ns,
            )
        request_meta.computed_tokens = computed_tokens
        request_meta.output_tokens = output_tokens
        request_meta.finish_time_ns = now_ns
        request_meta.state = status or "FINISHED"
        request_meta.last_update_time_ns = now_ns
        if hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)
        hint_runtime = self.hint_family_index.observe_finish(
            hints,
            output_tokens=output_tokens,
            now_ns=now_ns,
        )
        self.request_prefix_hits.pop(request_id, None)
        self.request_prompt_tokens.pop(request_id, None)
        payload = asdict(request_meta)
        if hint_runtime is not None:
            payload.update(hint_runtime.event_fields())
        self._emit("request_finished", **payload)
        self._flush_events()

    def on_request_scheduled(
        self,
        request_id: str,
        scheduled_tokens: int,
        num_computed_tokens: int,
        local_cached_tokens: int,
        external_cached_tokens: int,
        waiting_queue_size: int,
        running_queue_size: int,
        token_budget_before: int,
        token_budget_after: int,
        resumed: bool,
        load_kv_async: bool,
    ) -> None:
        if not self.enabled or not self.scheduler_trace:
            return
        now_ns = time.monotonic_ns()
        request_meta = self._get_or_create_request(request_id, now_ns=now_ns)
        request_meta.computed_tokens = num_computed_tokens
        request_meta.prefix_hit_tokens = max(
            request_meta.prefix_hit_tokens,
            local_cached_tokens + external_cached_tokens,
        )
        request_meta.last_update_time_ns = now_ns
        request_meta.state = "SCHEDULED_REMOTE_KV" if load_kv_async else "SCHEDULED"
        hints = self._get_request_hints(request_id)
        if hints is not None:
            self._apply_hints_to_request_meta(request_meta, hints)
        hint_runtime = self.hint_family_index.observe_schedule(
            hints,
            scheduled_tokens=scheduled_tokens,
            now_ns=now_ns,
        )
        payload = {
            "request_id": request_id,
            "scheduled_tokens": scheduled_tokens,
            "num_computed_tokens": num_computed_tokens,
            "local_cached_tokens": local_cached_tokens,
            "external_cached_tokens": external_cached_tokens,
            "waiting_queue_size": waiting_queue_size,
            "running_queue_size": running_queue_size,
            "token_budget_before": token_budget_before,
            "token_budget_after": token_budget_after,
            "resumed": resumed,
            "load_kv_async": load_kv_async,
            "request_class": request_meta.request_class,
            "family_id": request_meta.family_id,
            **self._hint_event_fields(request_id),
        }
        if hint_runtime is not None:
            payload.update(hint_runtime.event_fields())
        self._emit("request_scheduled", **payload)

    def reset(self) -> None:
        if not self.enabled:
            return
        self.blocks.clear()
        self.evicted_shadows.clear()
        self.request_prefix_hits.clear()
        self.request_prompt_tokens.clear()
        self.requests.clear()
        self.request_hints.clear()
        self.request_defer_reasons.clear()
        self.request_admission_limit_state.clear()
        self.family_index.clear()
        self.hint_family_index.clear()
        self._emit("lifecycle_reset")
        self._flush_events()
