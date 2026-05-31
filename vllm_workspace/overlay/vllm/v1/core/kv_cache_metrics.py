# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""KV cache metrics tracking."""

import random
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vllm.v1.core.kv_cache_utils import BlockHashWithGroupId, KVCacheBlock

from vllm.v1.metrics.stats import (
    KVCacheEvictionEvent,
    KVCacheEvictionRegretEvent,
    KVCacheLifecycleStats,
)


def _hash_to_hex(block_hash: "BlockHashWithGroupId | None") -> str | None:
    if block_hash is None:
        return None
    return bytes(block_hash).hex()


class BlockMetricsState:
    """Tracks lifecycle metrics for a single KV cache block."""

    def __init__(self):
        now_ns = time.monotonic_ns()
        self.birth_time_ns = now_ns
        self.last_access_ns = now_ns
        # Bounded to prevent unbounded growth if a block is accessed many times.
        self.access_history: deque[int] = deque(maxlen=4)
        self.access_count = 0
        self.hit_count = 0
        self.peak_ref_count = 0
        self.prefix_depth = 0
        self.recompute_cost_tokens = 0
        self.branch_factor = 0
        self.block_hash: str | None = None

    def record_cached(
        self,
        block_hash: "BlockHashWithGroupId | None",
        prefix_depth: int,
        recompute_cost_tokens: int,
        ref_cnt: int,
    ) -> None:
        self.block_hash = _hash_to_hex(block_hash)
        self.prefix_depth = max(self.prefix_depth, prefix_depth)
        self.recompute_cost_tokens = max(
            self.recompute_cost_tokens, recompute_cost_tokens
        )
        self.record_ref_count(ref_cnt)

    def record_access(self, ref_cnt: int, hit: bool = True) -> None:
        now_ns = time.monotonic_ns()
        self.last_access_ns = now_ns
        self.access_history.append(now_ns)
        self.access_count += 1
        if hit:
            self.hit_count += 1
            self.branch_factor += 1
        self.record_ref_count(ref_cnt)

    def record_ref_count(self, ref_cnt: int) -> None:
        self.peak_ref_count = max(self.peak_ref_count, ref_cnt)

    def get_lifetime_seconds(self) -> float:
        now_ns = time.monotonic_ns()
        return (now_ns - self.birth_time_ns) / 1e9

    def get_idle_time_seconds(self) -> float:
        now_ns = time.monotonic_ns()
        return (now_ns - self.last_access_ns) / 1e9

    def get_reuse_gaps_seconds(self) -> list[float]:
        if len(self.access_history) < 2:
            return []
        history = list(self.access_history)
        return [(history[i] - history[i - 1]) / 1e9 for i in range(1, len(history))]


class KVCacheMetricsCollector:
    """Collects KV cache residency metrics with sampling."""

    def __init__(self, sample_rate: float = 0.01):
        assert 0 < sample_rate <= 1.0, (
            f"sample_rate must be in (0, 1.0], got {sample_rate}"
        )
        self.sample_rate = sample_rate

        self.block_metrics: dict[int, BlockMetricsState] = {}

        self._eviction_events: list[KVCacheEvictionEvent] = []
        self._regret_events: list[KVCacheEvictionRegretEvent] = []
        self._recent_evictions_by_hash: dict[str, tuple[int, int, int]] = {}
        self._lifecycle_stats = KVCacheLifecycleStats()
        self._peak_active_blocks = 0

    def _record_metadata_overhead(self, start_ns: int) -> None:
        self._lifecycle_stats.metadata_update_time_seconds += (
            time.monotonic_ns() - start_ns
        ) / 1e9

    def should_sample_block(self) -> bool:
        return random.random() < self.sample_rate

    def on_block_allocated(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        try:
            self._lifecycle_stats.allocated_blocks += 1
            if self.should_sample_block():
                metrics = BlockMetricsState()
                metrics.record_ref_count(block.ref_cnt)
                self.block_metrics[block.block_id] = metrics
        finally:
            self._record_metadata_overhead(start_ns)

    def on_cache_lookup(self, hit: bool, elapsed_seconds: float) -> None:
        stats = self._lifecycle_stats
        stats.block_lookup_queries += 1
        if hit:
            stats.block_lookup_hits += 1
            stats.reused_blocks += 1
        stats.block_lookup_time_seconds += elapsed_seconds

    def on_block_cached(
        self,
        block: "KVCacheBlock",
        prefix_depth: int,
        block_size: int,
    ) -> None:
        start_ns = time.monotonic_ns()
        try:
            self._lifecycle_stats.cached_blocks += 1
            metrics = self.block_metrics.get(block.block_id)
            if metrics is None:
                return

            block_hash = _hash_to_hex(block.block_hash)
            if block_hash is not None:
                eviction_record = self._recent_evictions_by_hash.pop(block_hash, None)
                if eviction_record is not None:
                    evicted_time_ns, recompute_cost_tokens, evicted_prefix_depth = (
                        eviction_record
                    )
                    rebuild_gap_seconds = (
                        time.monotonic_ns() - evicted_time_ns
                    ) / 1e9
                    self._regret_events.append(
                        KVCacheEvictionRegretEvent(
                            rebuild_gap_seconds=rebuild_gap_seconds,
                            recompute_cost_tokens=recompute_cost_tokens,
                            prefix_depth=evicted_prefix_depth,
                        )
                    )

            metrics.record_cached(
                block.block_hash,
                prefix_depth=prefix_depth,
                recompute_cost_tokens=prefix_depth * block_size,
                ref_cnt=block.ref_cnt,
            )
        finally:
            self._record_metadata_overhead(start_ns)

    def on_block_accessed(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        try:
            metrics = self.block_metrics.get(block.block_id)
            if metrics:
                metrics.record_access(block.ref_cnt, hit=True)
        finally:
            self._record_metadata_overhead(start_ns)

    def on_block_ref_count_changed(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        try:
            metrics = self.block_metrics.get(block.block_id)
            if metrics:
                metrics.record_ref_count(block.ref_cnt)
        finally:
            self._record_metadata_overhead(start_ns)

    def on_block_evicted(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        try:
            self._lifecycle_stats.evicted_blocks += 1
            metrics = self.block_metrics.pop(block.block_id, None)
            if not metrics:
                return

            block_hash = metrics.block_hash or _hash_to_hex(block.block_hash)
            lifetime = metrics.get_lifetime_seconds()
            idle_time = metrics.get_idle_time_seconds()
            reuse_gaps = tuple(metrics.get_reuse_gaps_seconds())

            self._eviction_events.append(
                KVCacheEvictionEvent(
                    lifetime_seconds=lifetime,
                    idle_seconds=idle_time,
                    reuse_gaps_seconds=reuse_gaps,
                    access_count=metrics.access_count,
                    hit_count=metrics.hit_count,
                    peak_ref_count=metrics.peak_ref_count,
                    prefix_depth=metrics.prefix_depth,
                    recompute_cost_tokens=metrics.recompute_cost_tokens,
                    branch_factor=metrics.branch_factor,
                    block_hash=block_hash,
                )
            )
            if block_hash is not None:
                self._recent_evictions_by_hash[block_hash] = (
                    time.monotonic_ns(),
                    metrics.recompute_cost_tokens,
                    metrics.prefix_depth,
                )
        finally:
            self._record_metadata_overhead(start_ns)

    def update_pool_stats(
        self,
        free_blocks: int,
        total_blocks: int,
        active_blocks: int,
        cached_entries: int,
    ) -> None:
        stats = self._lifecycle_stats
        self._peak_active_blocks = max(self._peak_active_blocks, active_blocks)
        stats.free_blocks = free_blocks
        stats.total_blocks = total_blocks
        stats.active_blocks = active_blocks
        stats.peak_active_blocks = self._peak_active_blocks
        stats.cached_entries = cached_entries

    def update_waiting_stats(
        self,
        waiting_time_seconds: float,
        waiting_requests: int,
    ) -> None:
        stats = self._lifecycle_stats
        stats.waiting_time_seconds = waiting_time_seconds
        stats.waiting_requests = waiting_requests

    def reset(self) -> None:
        """Clear all state on cache reset."""
        self.block_metrics.clear()
        self._eviction_events.clear()
        self._regret_events.clear()
        self._recent_evictions_by_hash.clear()
        self._lifecycle_stats = KVCacheLifecycleStats()
        self._peak_active_blocks = 0

    def drain_events(self) -> list[KVCacheEvictionEvent]:
        events = self._eviction_events
        self._eviction_events = []
        return events

    def drain_regret_events(self) -> list[KVCacheEvictionRegretEvent]:
        events = self._regret_events
        self._regret_events = []
        return events

    def drain_lifecycle_stats(self) -> KVCacheLifecycleStats:
        stats = self._lifecycle_stats
        self._lifecycle_stats = KVCacheLifecycleStats(
            free_blocks=stats.free_blocks,
            total_blocks=stats.total_blocks,
            active_blocks=stats.active_blocks,
            peak_active_blocks=stats.peak_active_blocks,
            cached_entries=stats.cached_entries,
        )
        return stats
