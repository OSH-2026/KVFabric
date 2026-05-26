from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BlockRef:
    key: str
    prefix_depth: int
    family: str
    branch_tag: str


@dataclass(frozen=True)
class RequestSpec:
    request_id: str
    workload: str
    blocks: tuple[BlockRef, ...]
    decode_tokens: int


@dataclass
class BlockLife:
    key: str
    family: str
    prefix_depth: int
    first_seen_request: int
    last_access_request: int
    recompute_cost_tokens: int
    hit_count: int = 0
    miss_count: int = 0
    access_count: int = 0
    request_ids: set[str] = field(default_factory=set)
    branch_tags: set[str] = field(default_factory=set)

    @property
    def share_degree(self) -> int:
        return len(self.request_ids)

    @property
    def branch_factor(self) -> int:
        return len(self.branch_tags)


@dataclass
class EvictionEvent:
    event_id: int
    key: str
    policy: str
    workload: str
    evicted_at_request: int
    prefix_depth: int
    hit_count: int
    share_degree: int
    branch_factor: int
    recompute_cost_tokens: int
    regretted: bool = False
    rebuilt_at_request: int | None = None

    def to_json(self) -> dict:
        return {
            "event_id": self.event_id,
            "key": self.key,
            "policy": self.policy,
            "workload": self.workload,
            "evicted_at_request": self.evicted_at_request,
            "prefix_depth": self.prefix_depth,
            "hit_count": self.hit_count,
            "share_degree": self.share_degree,
            "branch_factor": self.branch_factor,
            "recompute_cost_tokens": self.recompute_cost_tokens,
            "regretted": self.regretted,
            "rebuilt_at_request": self.rebuilt_at_request,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run KVFabric lifecycle policy minimum-loop benchmark."
    )
    parser.add_argument("--config", required=True, help="Benchmark JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * pct))
    return ordered[index]


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.mean(values) if values else 0.0


def block_sequence(
    workload_name: str,
    request_index: int,
    shared: int,
    private: int,
    branch: str,
    branch_blocks: int = 0,
    cold_blocks: int = 0,
) -> tuple[BlockRef, ...]:
    blocks: list[BlockRef] = []
    depth = 1
    for i in range(shared):
        blocks.append(
            BlockRef(
                key=f"{workload_name}:shared:{i}",
                prefix_depth=depth,
                family="shared",
                branch_tag=branch,
            )
        )
        depth += 1
    for i in range(branch_blocks):
        blocks.append(
            BlockRef(
                key=f"{workload_name}:branch:{branch}:{i}",
                prefix_depth=depth,
                family="branch",
                branch_tag=branch,
            )
        )
        depth += 1
    for i in range(private):
        blocks.append(
            BlockRef(
                key=f"{workload_name}:private:{request_index}:{i}",
                prefix_depth=depth,
                family="private",
                branch_tag=branch,
            )
        )
        depth += 1
    for i in range(cold_blocks):
        blocks.append(
            BlockRef(
                key=f"{workload_name}:cold:{request_index}:{i}",
                prefix_depth=depth,
                family="cold_pressure",
                branch_tag=branch,
            )
        )
        depth += 1
    return tuple(blocks)


def generate_workload(workload: dict, decode_tokens: int) -> list[RequestSpec]:
    name = workload["name"]
    kind = workload["type"]
    requests: list[RequestSpec] = []

    if kind == "shared_prefix":
        total = int(workload["requests"])
        for idx in range(total):
            branch = f"user_{idx}"
            requests.append(
                RequestSpec(
                    request_id=f"{name}:{idx}",
                    workload=name,
                    blocks=block_sequence(
                        name,
                        idx,
                        shared=int(workload["shared_blocks"]),
                        private=int(workload["private_blocks"]),
                        branch=branch,
                    ),
                    decode_tokens=decode_tokens,
                )
            )
    elif kind == "template_fork":
        total = int(workload["requests"])
        branches = int(workload["branches"])
        for idx in range(total):
            branch = f"branch_{idx % branches}"
            requests.append(
                RequestSpec(
                    request_id=f"{name}:{idx}",
                    workload=name,
                    blocks=block_sequence(
                        name,
                        idx,
                        shared=int(workload["shared_blocks"]),
                        private=int(workload["private_blocks"]),
                        branch=branch,
                        branch_blocks=int(workload["branch_blocks"]),
                    ),
                    decode_tokens=decode_tokens,
                )
            )
    elif kind == "rag_long_context":
        total = int(workload["requests"])
        for idx in range(total):
            branch = f"question_{idx}"
            requests.append(
                RequestSpec(
                    request_id=f"{name}:{idx}",
                    workload=name,
                    blocks=block_sequence(
                        name,
                        idx,
                        shared=int(workload["shared_blocks"]),
                        private=int(workload["private_blocks"]),
                        branch=branch,
                    ),
                    decode_tokens=decode_tokens,
                )
            )
    elif kind == "cache_pressure":
        counter = 0
        rounds = int(workload["rounds"])
        for round_index in range(rounds):
            for hot_index in range(int(workload["hot_requests_per_round"])):
                branch = f"hot_{hot_index}"
                requests.append(
                    RequestSpec(
                        request_id=f"{name}:{counter}",
                        workload=name,
                        blocks=block_sequence(
                            name,
                            counter,
                            shared=int(workload["hot_shared_blocks"]),
                            private=int(workload["hot_private_blocks"]),
                            branch=branch,
                        ),
                        decode_tokens=decode_tokens,
                    )
                )
                counter += 1
            for cold_index in range(int(workload["cold_requests_per_round"])):
                branch = f"cold_{round_index}_{cold_index}"
                requests.append(
                    RequestSpec(
                        request_id=f"{name}:{counter}",
                        workload=name,
                        blocks=block_sequence(
                            name,
                            counter,
                            shared=0,
                            private=0,
                            branch=branch,
                            cold_blocks=int(workload["cold_blocks"]),
                        ),
                        decode_tokens=decode_tokens,
                    )
                )
                counter += 1
    else:
        raise ValueError(f"Unknown workload type: {kind}")

    return requests


class PolicySimulator:
    def __init__(self, config: dict, policy: str, workload_name: str):
        self.config = config
        self.policy = policy
        self.workload_name = workload_name
        self.block_size = int(config["block_size_tokens"])
        self.capacity = int(config["cache_blocks"])
        self.regret_window = int(config["regret_window_requests"])
        self.weights = config.get("shared_aware_weights", {})

        self.cache: dict[str, BlockLife] = {}
        self.side_table: dict[str, BlockLife] = {}
        self.evictions: list[EvictionEvent] = []
        self.evictions_by_key: dict[str, list[int]] = {}

        self.block_queries = 0
        self.block_hits = 0
        self.block_misses = 0
        self.usable_prefix_blocks = 0
        self.blocked_cached_blocks = 0
        self.requests = 0
        self.requests_with_any_hit = 0
        self.requests_with_full_prompt_hit = 0
        self.prompt_tokens_total = 0
        self.saved_prefill_tokens = 0
        self.computed_prefill_tokens = 0
        self.recomputed_tokens = 0
        self.regretted_recompute_tokens = 0
        self.peak_cached_blocks = 0
        self.policy_decision_seconds = 0.0
        self.ttft_samples: list[float] = []
        self.tpot_samples: list[float] = []
        self.request_latency_samples: list[float] = []

    def run(self, requests: list[RequestSpec]) -> dict:
        for request_index, request in enumerate(requests):
            self._handle_request(request_index, request)
        return self._metrics()

    def _handle_request(self, request_index: int, request: RequestSpec) -> None:
        self.requests += 1
        self.prompt_tokens_total += len(request.blocks) * self.block_size

        request_hits = 0
        request_misses = 0
        prefix_chain_intact = True

        for block in request.blocks:
            self.block_queries += 1
            state = self.side_table.get(block.key)
            seen_before = state is not None
            physical_hit = block.key in self.cache
            usable_hit = prefix_chain_intact and physical_hit

            if usable_hit:
                self.block_hits += 1
                request_hits += 1
                self.saved_prefill_tokens += self.block_size
                self.usable_prefix_blocks += 1
                self._record_access(block, request, request_index, hit=True)
                continue

            self.block_misses += 1
            request_misses += 1
            self.computed_prefill_tokens += self.block_size
            if seen_before:
                self.recomputed_tokens += self.block_size
            if physical_hit and not prefix_chain_intact:
                self.blocked_cached_blocks += 1
            if not physical_hit:
                if seen_before and self._mark_regret(block.key, request_index):
                    self.regretted_recompute_tokens += self.block_size
                state = self._record_access(block, request, request_index, hit=False)
                self._ensure_space_and_insert(block.key, request_index, state)
            else:
                self._record_access(block, request, request_index, hit=False)
            prefix_chain_intact = False

        if request_hits > 0:
            self.requests_with_any_hit += 1
        if request_misses == 0:
            self.requests_with_full_prompt_hit += 1

        self.peak_cached_blocks = max(self.peak_cached_blocks, len(self.cache))
        self._record_latency(request, request_misses)

    def _record_access(
        self,
        block: BlockRef,
        request: RequestSpec,
        request_index: int,
        hit: bool,
    ) -> BlockLife:
        state = self.side_table.get(block.key)
        if state is None:
            state = BlockLife(
                key=block.key,
                family=block.family,
                prefix_depth=block.prefix_depth,
                first_seen_request=request_index,
                last_access_request=request_index,
                recompute_cost_tokens=self.block_size * (block.prefix_depth + 1),
            )
            self.side_table[block.key] = state

        state.last_access_request = request_index
        state.access_count += 1
        state.request_ids.add(request.request_id)
        state.branch_tags.add(block.branch_tag)
        if hit:
            state.hit_count += 1
        else:
            state.miss_count += 1
        return state

    def _ensure_space_and_insert(
        self, key: str, request_index: int, state: BlockLife
    ) -> None:
        if len(self.cache) >= self.capacity:
            evict_key = self._choose_eviction_candidate(request_index)
            self._evict(evict_key, request_index)
        self.cache[key] = state

    def _choose_eviction_candidate(self, request_index: int) -> str:
        started = time.perf_counter()
        if self.policy == "lru":
            key = min(
                self.cache,
                key=lambda candidate: (
                    self.cache[candidate].last_access_request,
                    -self.cache[candidate].prefix_depth,
                ),
            )
        elif self.policy == "shared_aware":
            key = max(
                self.cache,
                key=lambda candidate: self._evict_score(
                    self.cache[candidate], request_index
                ),
            )
        else:
            raise ValueError(f"Unknown policy: {self.policy}")
        self.policy_decision_seconds += time.perf_counter() - started
        return key

    def _evict_score(self, state: BlockLife, request_index: int) -> float:
        age = max(0, request_index - state.last_access_request)
        hit_score = math.log1p(state.hit_count)
        share_score = math.log1p(state.share_degree)
        branch_score = math.log1p(state.branch_factor)
        depth_score = math.log1p(state.prefix_depth)
        recompute_score = state.recompute_cost_tokens / self.block_size
        return (
            float(self.weights.get("age", 1.0)) * age
            - float(self.weights.get("hit_count", 1.0)) * hit_score
            - float(self.weights.get("share_degree", 1.0))
            * (share_score + branch_score)
            - float(self.weights.get("prefix_depth", 0.5)) * depth_score
            - float(self.weights.get("recompute_cost", 0.5)) * recompute_score
        )

    def _evict(self, key: str, request_index: int) -> None:
        state = self.cache.pop(key)
        event = EvictionEvent(
            event_id=len(self.evictions),
            key=key,
            policy=self.policy,
            workload=self.workload_name,
            evicted_at_request=request_index,
            prefix_depth=state.prefix_depth,
            hit_count=state.hit_count,
            share_degree=state.share_degree,
            branch_factor=state.branch_factor,
            recompute_cost_tokens=state.recompute_cost_tokens,
        )
        self.evictions_by_key.setdefault(key, []).append(event.event_id)
        self.evictions.append(event)

    def _mark_regret(self, key: str, request_index: int) -> bool:
        for event_id in reversed(self.evictions_by_key.get(key, [])):
            event = self.evictions[event_id]
            if event.regretted:
                continue
            distance = request_index - event.evicted_at_request
            if 0 < distance <= self.regret_window:
                event.regretted = True
                event.rebuilt_at_request = request_index
                return True
            if distance > self.regret_window:
                return False
        return False

    def _record_latency(self, request: RequestSpec, request_misses: int) -> None:
        prefill_per_token = float(self.config["prefill_seconds_per_token"])
        decode_per_token = float(self.config["decode_seconds_per_token"])
        base_overhead = float(self.config["metadata_overhead_seconds_per_request"])
        if self.policy == "shared_aware":
            metadata_overhead = base_overhead
        else:
            metadata_overhead = base_overhead * 0.25

        computed_tokens = request_misses * self.block_size
        prefill_seconds = computed_tokens * prefill_per_token
        decode_seconds = request.decode_tokens * decode_per_token
        ttft = prefill_seconds + decode_per_token + metadata_overhead
        tpot = decode_per_token + (metadata_overhead / max(1, request.decode_tokens))
        latency = prefill_seconds + decode_seconds + metadata_overhead

        self.ttft_samples.append(ttft)
        self.tpot_samples.append(tpot)
        self.request_latency_samples.append(latency)

    def _metrics(self) -> dict:
        total_evictions = len(self.evictions)
        regretted_evictions = sum(1 for event in self.evictions if event.regretted)
        total_proxy_seconds = sum(self.request_latency_samples)
        unique_blocks = len(self.side_table)
        reused_blocks = sum(1 for state in self.side_table.values() if state.share_degree > 1)
        metadata_overhead = (
            float(self.config["metadata_overhead_seconds_per_request"])
            * self.requests
            * (1.0 if self.policy == "shared_aware" else 0.25)
        )

        return {
            "policy": self.policy,
            "workload": self.workload_name,
            "requests": self.requests,
            "cache_blocks": self.capacity,
            "block_size_tokens": self.block_size,
            "block_queries": self.block_queries,
            "block_hits": self.block_hits,
            "block_misses": self.block_misses,
            "prefix_block_hit_rate": self.block_hits / self.block_queries
            if self.block_queries
            else 0.0,
            "requests_with_any_hit_rate": self.requests_with_any_hit / self.requests
            if self.requests
            else 0.0,
            "requests_with_full_prompt_hit_rate": self.requests_with_full_prompt_hit
            / self.requests
            if self.requests
            else 0.0,
            "blocked_cached_blocks": self.blocked_cached_blocks,
            "prompt_tokens_total": self.prompt_tokens_total,
            "saved_prefill_tokens": self.saved_prefill_tokens,
            "computed_prefill_tokens": self.computed_prefill_tokens,
            "recomputed_tokens": self.recomputed_tokens,
            "regretted_recompute_tokens": self.regretted_recompute_tokens,
            "recompute_ratio": self.recomputed_tokens / self.prompt_tokens_total
            if self.prompt_tokens_total
            else 0.0,
            "total_evictions": total_evictions,
            "regretted_evictions": regretted_evictions,
            "eviction_regret_rate": regretted_evictions / total_evictions
            if total_evictions
            else 0.0,
            "unique_blocks_seen": unique_blocks,
            "reused_block_count": reused_blocks,
            "block_reuse_rate": reused_blocks / unique_blocks if unique_blocks else 0.0,
            "peak_cached_blocks": self.peak_cached_blocks,
            "peak_cache_usage": self.peak_cached_blocks / self.capacity
            if self.capacity
            else 0.0,
            "avg_ttft_seconds_proxy": mean(self.ttft_samples),
            "p95_ttft_seconds_proxy": percentile(self.ttft_samples, 0.95),
            "avg_tpot_seconds_proxy": mean(self.tpot_samples),
            "avg_request_latency_seconds_proxy": mean(self.request_latency_samples),
            "p95_request_latency_seconds_proxy": percentile(
                self.request_latency_samples, 0.95
            ),
            "request_throughput_proxy": self.requests / total_proxy_seconds
            if total_proxy_seconds
            else 0.0,
            "metadata_overhead_seconds_proxy": metadata_overhead,
            "policy_decision_seconds_measured": self.policy_decision_seconds,
            "eviction_events": [event.to_json() for event in self.evictions],
        }


def compare(shared: dict, lru: dict) -> dict:
    def delta(metric: str) -> float:
        return shared.get(metric, 0.0) - lru.get(metric, 0.0)

    def pct_delta(metric: str) -> float:
        base = lru.get(metric, 0.0)
        if not base:
            return 0.0
        return (shared.get(metric, 0.0) - base) / base

    return {
        "prefix_block_hit_rate_delta": delta("prefix_block_hit_rate"),
        "saved_prefill_tokens_delta": delta("saved_prefill_tokens"),
        "recomputed_tokens_delta": delta("recomputed_tokens"),
        "eviction_regret_rate_delta": delta("eviction_regret_rate"),
        "avg_ttft_seconds_proxy_delta": delta("avg_ttft_seconds_proxy"),
        "avg_ttft_seconds_proxy_pct_delta": pct_delta("avg_ttft_seconds_proxy"),
        "request_throughput_proxy_pct_delta": pct_delta("request_throughput_proxy"),
    }


def aggregate(policy: str, workload_metrics: list[dict]) -> dict:
    sums = {
        "requests": sum(item["requests"] for item in workload_metrics),
        "block_queries": sum(item["block_queries"] for item in workload_metrics),
        "block_hits": sum(item["block_hits"] for item in workload_metrics),
        "prompt_tokens_total": sum(
            item["prompt_tokens_total"] for item in workload_metrics
        ),
        "saved_prefill_tokens": sum(
            item["saved_prefill_tokens"] for item in workload_metrics
        ),
        "recomputed_tokens": sum(item["recomputed_tokens"] for item in workload_metrics),
        "total_evictions": sum(item["total_evictions"] for item in workload_metrics),
        "regretted_evictions": sum(
            item["regretted_evictions"] for item in workload_metrics
        ),
        "metadata_overhead_seconds_proxy": sum(
            item["metadata_overhead_seconds_proxy"] for item in workload_metrics
        ),
        "policy_decision_seconds_measured": sum(
            item["policy_decision_seconds_measured"] for item in workload_metrics
        ),
    }
    return {
        "policy": policy,
        **sums,
        "prefix_block_hit_rate": sums["block_hits"] / sums["block_queries"]
        if sums["block_queries"]
        else 0.0,
        "eviction_regret_rate": sums["regretted_evictions"] / sums["total_evictions"]
        if sums["total_evictions"]
        else 0.0,
        "recompute_ratio": sums["recomputed_tokens"] / sums["prompt_tokens_total"]
        if sums["prompt_tokens_total"]
        else 0.0,
        "avg_ttft_seconds_proxy": mean(
            item["avg_ttft_seconds_proxy"] for item in workload_metrics
        ),
        "avg_tpot_seconds_proxy": mean(
            item["avg_tpot_seconds_proxy"] for item in workload_metrics
        ),
        "request_throughput_proxy": mean(
            item["request_throughput_proxy"] for item in workload_metrics
        ),
    }


def build_markdown(result: dict) -> str:
    lines = [
        "# KVFabric 生命周期策略最小闭环",
        "",
        f"配置：`{result['config_name']}`",
        f"生成时间：`{result['generated_at']}`",
        "",
        "## 策略汇总对比",
        "",
        "| 策略 | 命中率 | 节省 tokens | 重算 tokens | 驱逐次数 | 后悔率 | 平均 TTFT 代理 | 请求吞吐代理 |",
        "|:--|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for policy in result["policy_order"]:
        item = result["aggregate"][policy]
        lines.append(
            f"| {policy} | {item['prefix_block_hit_rate']:.3f} | "
            f"{item['saved_prefill_tokens']} | "
            f"{item['recomputed_tokens']} | "
            f"{item['total_evictions']} | "
            f"{item['eviction_regret_rate']:.3f} | "
            f"{item['avg_ttft_seconds_proxy']:.4f} | "
            f"{item['request_throughput_proxy']:.2f} |"
        )

    comparison = result["aggregate_comparison"]
    lines += [
        "",
        "## Shared-Aware 相对 LRU 的变化",
        "",
        f"- 命中率变化：{comparison['prefix_block_hit_rate_delta']:+.3f}",
        f"- 节省 prefill tokens 变化：{comparison['saved_prefill_tokens_delta']:+.0f}",
        f"- 重算 tokens 变化：{comparison['recomputed_tokens_delta']:+.0f}",
        f"- 驱逐后悔率变化：{comparison['eviction_regret_rate_delta']:+.3f}",
        f"- 平均 TTFT 代理变化：{comparison['avg_ttft_seconds_proxy_delta']:+.4f}s",
        f"- 吞吐代理变化：{comparison['request_throughput_proxy_pct_delta']:+.1%}",
        "",
        "## 分负载指标",
        "",
        "| 负载 | 策略 | 命中率 | 节省 | 重算 | 驱逐次数 | 后悔率 | P95 TTFT 代理 |",
        "|:--|:--|--:|--:|--:|--:|--:|--:|",
    ]
    for workload_name, policies in result["workloads"].items():
        for policy in result["policy_order"]:
            item = policies[policy]
            lines.append(
                f"| {workload_name} | {policy} | "
                f"{item['prefix_block_hit_rate']:.3f} | "
                f"{item['saved_prefill_tokens']} | "
                f"{item['recomputed_tokens']} | "
                f"{item['total_evictions']} | "
                f"{item['eviction_regret_rate']:.3f} | "
                f"{item['p95_ttft_seconds_proxy']:.4f} |"
            )

    lines += [
        "",
        "## 闭环覆盖范围",
        "",
        "- 负载生成器：完全共享前缀、模板分叉、RAG 长上下文、缓存压力。",
        "- 生命周期 side table：命中次数、共享度、分叉度、前缀深度、重算代价、驱逐历史。",
        "- 策略：原始 LRU 近似策略与 KVFabric 共享感知驱逐评分器。",
        "- 指标：前缀 block 命中率、节省的 prefill tokens、重算 tokens、驱逐后悔率、缓存使用率、TTFT/TPOT 代理值、策略决策时间。",
        "",
        "## 局限性",
        "",
        "这次运行是确定性的 Python 层原型。它验证的是控制面策略闭环和指标定义，不能替代下一步基于真实 GPU /metrics 与请求延迟的 vLLM 实验。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    shutil.copy2(config_path, output_dir / "config.json")

    decode_tokens = int(config["decode_tokens_per_request"])
    policy_order = list(config["policies"])
    workloads: dict[str, dict[str, dict]] = {}
    events: list[dict] = []

    for workload in config["workloads"]:
        requests = generate_workload(workload, decode_tokens)
        workload_metrics: dict[str, dict] = {}
        for policy in policy_order:
            simulator = PolicySimulator(config, policy, workload["name"])
            metrics = simulator.run(requests)
            workload_metrics[policy] = {
                key: value for key, value in metrics.items() if key != "eviction_events"
            }
            for event in metrics["eviction_events"]:
                events.append(event)
        workloads[workload["name"]] = workload_metrics

    aggregate_by_policy = {
        policy: aggregate(
            policy,
            [workload_metrics[policy] for workload_metrics in workloads.values()],
        )
        for policy in policy_order
    }

    result = {
        "config_name": config.get("name", config_path.stem),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "policy_order": policy_order,
        "aggregate": aggregate_by_policy,
        "aggregate_comparison": compare(
            aggregate_by_policy["shared_aware"], aggregate_by_policy["lru"]
        ),
        "workloads": workloads,
    }

    (output_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "eviction_events.jsonl").open("w", encoding="utf-8") as event_file:
        for event in events:
            event_file.write(json.dumps(event, ensure_ascii=False) + "\n")
    (output_dir / "summary.md").write_text(build_markdown(result), encoding="utf-8")

    print(json.dumps(result["aggregate_comparison"], ensure_ascii=False, indent=2))
    print(f"Run output: {output_dir}")


if __name__ == "__main__":
    main()
