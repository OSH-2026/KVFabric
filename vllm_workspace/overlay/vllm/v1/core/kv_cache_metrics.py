# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""KV cache metrics tracking."""

import random
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vllm.v1.core.kv_cache_utils import KVCacheBlock

from vllm.v1.metrics.stats import KVCacheEvictionEvent, KVCacheLifecycleStats


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

    def record_access(self) -> None:
        now_ns = time.monotonic_ns()
        self.last_access_ns = now_ns
        self.access_history.append(now_ns)
        self.access_count += 1

    def update_from_block(self, block: "KVCacheBlock") -> None:
        self.peak_ref_count = max(self.peak_ref_count, block.ref_cnt)
        if block.block_hash is not None:
            self.block_hash = str(block.block_hash)

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
        self._lifecycle_stats = KVCacheLifecycleStats()

    def should_sample_block(self) -> bool:
        return random.random() < self.sample_rate

    def on_block_allocated(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        self._lifecycle_stats.allocated_blocks += 1
        if self.should_sample_block():
            metrics = BlockMetricsState()
            metrics.update_from_block(block)
            self.block_metrics[block.block_id] = metrics
        self._lifecycle_stats.metadata_update_time_seconds += (
            time.monotonic_ns() - start_ns
        ) / 1e9

    def on_block_cached(
        self,
        block: "KVCacheBlock",
        prefix_depth: int,
        block_size: int,
    ) -> None:
        start_ns = time.monotonic_ns()
        self._lifecycle_stats.cached_blocks += 1
        metrics = self.block_metrics.get(block.block_id)
        if metrics:
            metrics.prefix_depth = prefix_depth
            metrics.recompute_cost_tokens = prefix_depth * block_size
            metrics.update_from_block(block)
        self._lifecycle_stats.metadata_update_time_seconds += (
            time.monotonic_ns() - start_ns
        ) / 1e9

    def on_block_accessed(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        self._lifecycle_stats.reused_blocks += 1
        metrics = self.block_metrics.get(block.block_id)
        if metrics:
            metrics.record_access()
            metrics.hit_count += 1
            metrics.update_from_block(block)
        self._lifecycle_stats.metadata_update_time_seconds += (
            time.monotonic_ns() - start_ns
        ) / 1e9

    def on_cache_lookup(self, hit: bool, elapsed_seconds: float = 0.0) -> None:
        self._lifecycle_stats.block_lookup_queries += 1
        if hit:
            self._lifecycle_stats.block_lookup_hits += 1
        self._lifecycle_stats.block_lookup_time_seconds += elapsed_seconds

    def update_pool_stats(
        self,
        free_blocks: int,
        total_blocks: int,
        active_blocks: int,
        cached_entries: int,
    ) -> None:
        stats = self._lifecycle_stats
        stats.free_blocks = free_blocks
        stats.total_blocks = total_blocks
        stats.active_blocks = active_blocks
        stats.peak_active_blocks = max(stats.peak_active_blocks, active_blocks)
        stats.cached_entries = cached_entries

    def on_block_evicted(self, block: "KVCacheBlock") -> None:
        start_ns = time.monotonic_ns()
        self._lifecycle_stats.evicted_blocks += 1
        metrics = self.block_metrics.pop(block.block_id, None)
        if not metrics:
            self._lifecycle_stats.metadata_update_time_seconds += (
                time.monotonic_ns() - start_ns
            ) / 1e9
            return
        metrics.update_from_block(block)

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
                block_hash=metrics.block_hash,
            )
        )
        self._lifecycle_stats.metadata_update_time_seconds += (
            time.monotonic_ns() - start_ns
        ) / 1e9

    def reset(self) -> None:
        """Clear all state on cache reset."""
        self.block_metrics.clear()
        self._eviction_events.clear()
        self._lifecycle_stats = KVCacheLifecycleStats()

    def drain_events(self) -> list[KVCacheEvictionEvent]:
        events = self._eviction_events
        self._eviction_events = []
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
