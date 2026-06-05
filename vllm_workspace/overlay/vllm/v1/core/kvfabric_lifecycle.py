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

if TYPE_CHECKING:
    from vllm.v1.core.kv_cache_utils import BlockHashWithGroupId, KVCacheBlock


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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


class KVFabricLifecycleTracker:
    """Tracks OS-style KV block lifecycle metadata for KVFabric experiments."""

    def __init__(self, enabled: bool, log_path: str | None = None) -> None:
        self.enabled = enabled
        self.log_path = Path(log_path).expanduser() if log_path else None
        self.eviction_policy = os.environ.get(
            "KVFABRIC_EVICTION_POLICY", "lru"
        ).strip().lower()
        self.admission_min_free_ratio = float(
            os.environ.get("KVFABRIC_ADMISSION_MIN_FREE_RATIO", "0.20")
        )
        self.admission_anchor_blocks = int(
            os.environ.get("KVFABRIC_ADMISSION_ANCHOR_BLOCKS", "8")
        )
        self.admission_min_prompt_tokens = int(
            os.environ.get("KVFABRIC_ADMISSION_MIN_PROMPT_TOKENS", "800")
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
        self._event_seq = 0

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

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

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
    ) -> None:
        if not self.enabled or block.is_null:
            return

        block_hash = _hash_to_hex(block.block_hash)
        meta = self._get_or_create(block)
        meta.block_hash = block_hash
        meta.prefix_depth = max(meta.prefix_depth, prefix_depth)
        meta.recompute_cost_tokens = max(
            meta.recompute_cost_tokens, prefix_depth * block_size
        )
        meta.ref_count = block.ref_cnt
        meta.share_degree = max(meta.share_degree, block.ref_cnt)
        meta.state = "SHARED" if block.ref_cnt > 1 else "SEALED"
        meta.last_access_time_ns = time.monotonic_ns()

        rebuilt_from_eviction = False
        rebuild_gap_seconds = 0.0
        if block_hash is not None:
            shadow = self.evicted_shadows.pop(block_hash, None)
            if shadow is not None:
                rebuilt_from_eviction = True
                rebuild_gap_seconds = (
                    time.monotonic_ns() - shadow.evicted_time_ns
                ) / 1e9

        self._emit(
            "block_sealed",
            rebuilt_from_eviction=rebuilt_from_eviction,
            rebuild_gap_seconds=rebuild_gap_seconds,
            retain_score=self._retain_score(meta),
            **asdict(meta),
        )

    def on_block_touched(self, block: "KVCacheBlock", from_free_queue: bool) -> None:
        if not self.enabled or block.is_null:
            return

        meta = self._get_or_create(block)
        meta.block_hash = meta.block_hash or _hash_to_hex(block.block_hash)
        meta.ref_count = block.ref_cnt
        meta.hit_count += 1
        meta.share_degree = max(meta.share_degree, block.ref_cnt)
        meta.branch_factor = max(meta.branch_factor, meta.share_degree - 1)
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
            )

        self._emit("block_evicted", retain_score=retain_score, **asdict(meta))

    def on_prefix_lookup(
        self,
        request_id: str,
        prompt_tokens: int,
        hit_tokens: int,
        skipped: bool,
        max_cache_hit_length: int,
    ) -> None:
        if not self.enabled:
            return
        self.request_prefix_hits[request_id] = hit_tokens
        self.request_prompt_tokens[request_id] = prompt_tokens
        self._emit(
            "prefix_lookup",
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            hit_tokens=hit_tokens,
            skipped=skipped,
            max_cache_hit_length=max_cache_hit_length,
            hit=hit_tokens > 0,
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
    ) -> int:
        if self.eviction_policy != "family_protect" or total_blocks <= 0:
            return num_full_blocks

        free_ratio = free_blocks / total_blocks
        request_hit_tokens = self.request_prefix_hits.get(request_id, 0)
        request_prompt_tokens = self.request_prompt_tokens.get(request_id, 0)
        if request_prompt_tokens < self.admission_min_prompt_tokens:
            return num_full_blocks
        if request_hit_tokens > 0 and free_ratio >= self.admission_min_free_ratio:
            return num_full_blocks

        limited = min(
            num_full_blocks,
            max(num_cached_blocks, self.admission_anchor_blocks),
        )
        if limited < num_full_blocks:
            self._emit(
                "cache_admission_limited",
                request_id=request_id,
                request_hit_tokens=request_hit_tokens,
                request_prompt_tokens=request_prompt_tokens,
                num_cached_blocks=num_cached_blocks,
                original_full_blocks=num_full_blocks,
                limited_full_blocks=limited,
                free_blocks=free_blocks,
                total_blocks=total_blocks,
                free_ratio=free_ratio,
            )
        return limited

    def get_retain_score(self, block: "KVCacheBlock") -> float:
        meta = self.blocks.get(block.block_id)
        if meta is None:
            return 0.0
        return self._retain_score(meta)

    def _retain_score(self, meta: LifecycleBlockMeta) -> float:
        return meta.retain_score(
            use_reuse=self.retain_use_reuse,
            use_prefix=self.retain_use_prefix,
            use_recompute=self.retain_use_recompute,
        )

    def is_protected(self, block: "KVCacheBlock") -> bool:
        meta = self.blocks.get(block.block_id)
        if meta is None:
            return False
        return (
            meta.hit_count >= self.protect_min_hit_count
            or meta.share_degree >= self.protect_min_share_degree
            or meta.branch_factor >= self.protect_min_branch_factor
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
                }
                for block in selected[:16]
            ]
        self._emit("eviction_candidates_ranked", **payload)
        return selected

    def reset(self) -> None:
        if not self.enabled:
            return
        self.blocks.clear()
        self.evicted_shadows.clear()
        self.request_prefix_hits.clear()
        self.request_prompt_tokens.clear()
        self._emit("lifecycle_reset")
