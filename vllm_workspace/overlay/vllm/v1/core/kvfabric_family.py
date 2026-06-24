# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Prefix-family metadata for KVFabric lifecycle experiments."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PrefixNodeMeta:
    block_hash: str
    family_id: int
    root_hash: str
    parent_hash: str | None
    depth: int
    first_seen_ns: int
    last_seen_ns: int
    children: set[str] = field(default_factory=set)
    hit_count: int = 0
    seal_count: int = 0
    evict_count: int = 0
    rebuild_count: int = 0
    regret_count: int = 0

    @property
    def branch_count(self) -> int:
        return len(self.children)


@dataclass
class PrefixFamilyMeta:
    family_id: int
    root_hash: str
    first_seen_ns: int
    last_seen_ns: int
    hit_count: int = 0
    sealed_blocks: int = 0
    evicted_blocks: int = 0
    rebuilt_blocks: int = 0
    regret_count: int = 0
    max_depth: int = 0
    protected_depth: int = 0


class PrefixFamilyIndex:
    """Tracks explicit prefix-tree lineage by block hash.

    vLLM already computes stable block hashes for block-aligned prefixes. This
    side index uses the adjacent hashes observed while blocks are sealed to
    build parent/child edges without changing cache lookup semantics.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, PrefixNodeMeta] = {}
        self.families: dict[int, PrefixFamilyMeta] = {}
        self._root_to_family_id: dict[str, int] = {}
        self._next_family_id = 1

    def clear(self) -> None:
        self.nodes.clear()
        self.families.clear()
        self._root_to_family_id.clear()
        self._next_family_id = 1

    def observe_block(
        self,
        block_hash: str,
        parent_hash: str | None,
        root_hash: str | None,
        depth: int,
        rebuilt_from_eviction: bool = False,
        now_ns: int | None = None,
    ) -> tuple[PrefixNodeMeta, PrefixFamilyMeta]:
        now_ns = now_ns or time.monotonic_ns()
        root_hash = root_hash or block_hash

        parent_node = self.nodes.get(parent_hash) if parent_hash else None
        if parent_node is not None:
            family_id = parent_node.family_id
            root_hash = parent_node.root_hash
        else:
            family_id = self._root_to_family_id.get(root_hash, 0)
            if family_id == 0:
                family_id = self._next_family_id
                self._next_family_id += 1
                self._root_to_family_id[root_hash] = family_id

        family = self.families.get(family_id)
        if family is None:
            family = PrefixFamilyMeta(
                family_id=family_id,
                root_hash=root_hash,
                first_seen_ns=now_ns,
                last_seen_ns=now_ns,
            )
            self.families[family_id] = family

        node = self.nodes.get(block_hash)
        if node is None:
            node = PrefixNodeMeta(
                block_hash=block_hash,
                family_id=family_id,
                root_hash=root_hash,
                parent_hash=parent_hash,
                depth=depth,
                first_seen_ns=now_ns,
                last_seen_ns=now_ns,
            )
            self.nodes[block_hash] = node
        else:
            node.family_id = family_id
            node.root_hash = root_hash
            node.parent_hash = node.parent_hash or parent_hash
            node.depth = max(node.depth, depth)
            node.last_seen_ns = now_ns

        if parent_hash and parent_hash != block_hash:
            parent = self.nodes.get(parent_hash)
            if parent is not None:
                parent.children.add(block_hash)
                parent.last_seen_ns = now_ns

        node.seal_count += 1
        if rebuilt_from_eviction:
            node.rebuild_count += 1
            node.regret_count += 1
            family.rebuilt_blocks += 1
            family.regret_count += 1

        family.sealed_blocks += 1
        family.max_depth = max(family.max_depth, depth)
        family.protected_depth = max(family.protected_depth, self._protected_depth(family))
        family.last_seen_ns = now_ns
        return node, family

    def touch(
        self,
        block_hash: str,
        now_ns: int | None = None,
    ) -> tuple[PrefixNodeMeta | None, PrefixFamilyMeta | None]:
        now_ns = now_ns or time.monotonic_ns()
        node = self.nodes.get(block_hash)
        if node is None:
            return None, None
        node.hit_count += 1
        node.last_seen_ns = now_ns
        family = self.families.get(node.family_id)
        if family is not None:
            family.hit_count += 1
            family.protected_depth = max(
                family.protected_depth, self._protected_depth(family)
            )
            family.last_seen_ns = now_ns
        return node, family

    def evict(
        self,
        block_hash: str,
        now_ns: int | None = None,
    ) -> tuple[PrefixNodeMeta | None, PrefixFamilyMeta | None]:
        now_ns = now_ns or time.monotonic_ns()
        node = self.nodes.get(block_hash)
        if node is None:
            return None, None
        node.evict_count += 1
        node.last_seen_ns = now_ns
        family = self.families.get(node.family_id)
        if family is not None:
            family.evicted_blocks += 1
            family.last_seen_ns = now_ns
        return node, family

    def get_node(self, block_hash: str | None) -> PrefixNodeMeta | None:
        if block_hash is None:
            return None
        return self.nodes.get(block_hash)

    def get_family(self, family_id: int | None) -> PrefixFamilyMeta | None:
        if family_id is None:
            return None
        return self.families.get(family_id)

    def family_value(self, block_hash: str | None) -> float:
        node = self.get_node(block_hash)
        if node is None:
            return 0.0
        family = self.families.get(node.family_id)
        if family is None:
            return 0.0
        return (
            2.0 * min(family.hit_count, 32)
            + 4.0 * min(node.branch_count, 8)
            + 6.0 * min(family.regret_count, 16)
            + 1.0 * min(family.protected_depth, 16)
        )

    def event_payload(self, block_hash: str | None) -> dict[str, int | str | None]:
        node = self.get_node(block_hash)
        if node is None:
            return {
                "family_id": None,
                "root_hash": None,
                "parent_hash": None,
                "family_hit_count": 0,
                "family_branch_count": 0,
                "family_regret_count": 0,
                "protected_depth": 0,
            }
        family = self.families.get(node.family_id)
        return {
            "family_id": node.family_id,
            "root_hash": node.root_hash,
            "parent_hash": node.parent_hash,
            "family_hit_count": family.hit_count if family else 0,
            "family_branch_count": node.branch_count,
            "family_regret_count": family.regret_count if family else 0,
            "protected_depth": family.protected_depth if family else 0,
        }

    def _protected_depth(self, family: PrefixFamilyMeta) -> int:
        if family.hit_count <= 0 and family.regret_count <= 0:
            return 0
        if family.hit_count >= 8 or family.regret_count > 0:
            return min(max(family.max_depth, 1), 8)
        if family.hit_count >= 2:
            return min(max(family.max_depth, 1), 4)
        return min(max(family.max_depth, 1), 2)
