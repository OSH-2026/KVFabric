#!/usr/bin/env python3
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kvfabric_run_reader import read_jsonl


STATE_ORDER = {
    "FREE": 0,
    "ACTIVE": 1,
    "SEALED": 2,
    "SHARED": 3,
    "COOLING_WARM": 4,
    "COOLING_HOT": 5,
    "EVICTED": 6,
    "REBUILT": 7,
}

STATE_COLORS = {
    "FREE": "#1f2937",
    "ACTIVE": "#2563eb",
    "SEALED": "#06b6d4",
    "SHARED": "#22c55e",
    "COOLING_WARM": "#eab308",
    "COOLING_HOT": "#f97316",
    "EVICTED": "#ef4444",
    "REBUILT": "#a855f7",
}


@dataclass
class BlockState:
    block_id: int
    state: str = "FREE"
    prefix_depth: int = 0
    hit_count: int = 0
    share_degree: int = 0
    retain_score: float = 0.0
    family_id: int | None = None
    last_event: str = ""
    last_time_ns: int = 0
    rebuilt_flash_until_ns: int = 0

    def display_state(self) -> str:
        if self.rebuilt_flash_until_ns and self.last_time_ns <= self.rebuilt_flash_until_ns:
            return "REBUILT"
        return self.state

    def intensity(self) -> float:
        return min(
            1.0,
            0.25
            + math.log1p(max(self.hit_count, 0)) * 0.18
            + min(max(self.share_degree, 0), 8) * 0.05
            + min(max(self.retain_score, 0.0), 80.0) / 320.0,
        )


@dataclass
class ReplayState:
    blocks: dict[int, BlockState] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: {
        "events": 0,
        "prefix_query_tokens": 0,
        "prefix_hit_tokens": 0,
        "evicted_blocks": 0,
        "sealed_blocks": 0,
        "rebuilt_from_eviction": 0,
        "admission_limited": 0,
        "admission_saved_blocks": 0,
        "scheduler_defers": 0,
        "scheduler_promotes": 0,
        "scheduler_latency_promotes": 0,
    })
    first_time_ns: int = 0
    last_time_ns: int = 0
    current_request: dict[str, Any] = field(default_factory=dict)
    bad_lines: int = 0

    @property
    def elapsed_seconds(self) -> float:
        if self.first_time_ns <= 0 or self.last_time_ns <= 0:
            return 0.0
        return max(self.last_time_ns - self.first_time_ns, 0) / 1e9

    @property
    def prefix_hit_rate(self) -> float:
        query = self.counters["prefix_query_tokens"]
        return self.counters["prefix_hit_tokens"] / query if query else 0.0


def _event_time(event: dict[str, Any]) -> int:
    try:
        return int(event.get("time_ns") or 0)
    except (TypeError, ValueError):
        return 0


def _int(event: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(event.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _float(event: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(event.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def apply_event(state: ReplayState, event: dict[str, Any]) -> None:
    event_name = str(event.get("event", "unknown"))
    time_ns = _event_time(event)
    if state.first_time_ns <= 0 and time_ns > 0:
        state.first_time_ns = time_ns
    if time_ns > 0:
        state.last_time_ns = time_ns
    state.counters["events"] += 1

    block_id_raw = event.get("block_id")
    if block_id_raw is not None:
        block_id = _int(event, "block_id")
        block = state.blocks.get(block_id)
        if block is None:
            block = BlockState(block_id=block_id)
            state.blocks[block_id] = block
        block.last_event = event_name
        block.last_time_ns = time_ns
        block.state = str(event.get("state") or block.state or "FREE")
        block.prefix_depth = _int(event, "prefix_depth", block.prefix_depth)
        block.hit_count = _int(event, "hit_count", block.hit_count)
        block.share_degree = _int(event, "share_degree", block.share_degree)
        block.retain_score = _float(event, "retain_score", block.retain_score)
        if event.get("family_id") is not None:
            block.family_id = _int(event, "family_id")
        if event_name == "block_allocated" and event.get("block_hash") is None:
            block.state = "ACTIVE"
        if event_name == "block_evicted":
            block.state = "EVICTED"
            state.counters["evicted_blocks"] += 1
        if event_name == "block_sealed":
            state.counters["sealed_blocks"] += 1
            if event.get("rebuilt_from_eviction"):
                state.counters["rebuilt_from_eviction"] += 1
                block.rebuilt_flash_until_ns = time_ns + 1_000_000_000

    if event_name == "prefix_lookup":
        state.counters["prefix_query_tokens"] += _int(event, "prompt_tokens")
        state.counters["prefix_hit_tokens"] += _int(event, "hit_tokens")
        state.current_request = {
            "request_id": event.get("request_id"),
            "trace_request_id": event.get("hint_trace_request_id"),
            "request_class": event.get("hint_request_class")
            or event.get("request_class"),
            "family_key": event.get("hint_family_key"),
            "cache_priority": event.get("hint_cache_priority"),
            "expected_reuse": event.get("hint_expected_reuse"),
        }
    elif event_name == "cache_admission_limited":
        state.counters["admission_limited"] += 1
        original = _int(event, "original_full_blocks")
        limited = _int(event, "limited_full_blocks")
        state.counters["admission_saved_blocks"] += max(original - limited, 0)
    elif event_name == "request_deferred":
        state.counters["scheduler_defers"] += 1
    elif event_name == "request_promoted":
        state.counters["scheduler_promotes"] += 1
    elif event_name == "request_latency_promoted":
        state.counters["scheduler_latency_promotes"] += 1


def load_replay_state(
    lifecycle_path: Path,
    limit_events: int | None = 100000,
) -> ReplayState:
    events, bad_lines = read_jsonl(lifecycle_path, limit=limit_events)
    state = ReplayState(bad_lines=bad_lines)
    for event in events:
        apply_event(state, event)
    return state


def block_grid_matrix(state: ReplayState) -> tuple[list[list[int]], list[list[str]], list[str]]:
    if not state.blocks:
        return [[0]], [["No block events"]], ["FREE"]
    block_ids = sorted(state.blocks)
    width = max(8, math.ceil(math.sqrt(len(block_ids))))
    height = math.ceil(len(block_ids) / width)
    z: list[list[int]] = []
    text: list[list[str]] = []
    labels = list(STATE_ORDER)
    for row in range(height):
        z_row = []
        text_row = []
        for col in range(width):
            idx = row * width + col
            if idx >= len(block_ids):
                z_row.append(0)
                text_row.append("")
                continue
            block = state.blocks[block_ids[idx]]
            display_state = block.display_state()
            z_row.append(STATE_ORDER.get(display_state, 0))
            text_row.append(
                f"block {block.block_id}<br>"
                f"state={display_state}<br>"
                f"depth={block.prefix_depth}<br>"
                f"hits={block.hit_count}<br>"
                f"share={block.share_degree}<br>"
                f"retain={block.retain_score:.1f}<br>"
                f"family={block.family_id}"
            )
        z.append(z_row)
        text.append(text_row)
    return z, text, labels


def make_block_grid_figure(state: ReplayState, title: str = "KV Block Grid"):
    import plotly.graph_objects as go

    z, text, labels = block_grid_matrix(state)
    colorscale = [
        [idx / max(len(labels) - 1, 1), STATE_COLORS[label]]
        for idx, label in enumerate(labels)
    ]
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            text=text,
            hoverinfo="text",
            zmin=0,
            zmax=max(len(labels) - 1, 1),
            colorscale=colorscale,
            showscale=True,
            colorbar=dict(
                tickmode="array",
                tickvals=list(range(len(labels))),
                ticktext=labels,
            ),
        )
    )
    fig.update_layout(
        title=title,
        paper_bgcolor="#0b1020",
        plot_bgcolor="#0b1020",
        font=dict(color="#e5e7eb"),
        margin=dict(l=20, r=20, t=55, b=20),
        height=460,
    )
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, showticklabels=False, autorange="reversed")
    return fig


def make_event_timeline_figure(
    lifecycle_path: Path,
    limit_events: int = 12000,
    title: str = "KV Lifecycle Timeline",
):
    import plotly.graph_objects as go

    events, _ = read_jsonl(lifecycle_path, limit=limit_events)
    if not events:
        return go.Figure()
    first_time = next((_event_time(event) for event in events if _event_time(event)), 0)
    xs: list[float] = []
    ys: list[int] = []
    colors: list[str] = []
    texts: list[str] = []
    for event in events:
        if event.get("block_id") is None:
            continue
        state_name = str(event.get("state") or "FREE")
        if event.get("event") == "block_evicted":
            state_name = "EVICTED"
        if event.get("event") == "block_sealed" and event.get("rebuilt_from_eviction"):
            state_name = "REBUILT"
        xs.append((_event_time(event) - first_time) / 1e9 if first_time else 0.0)
        ys.append(_int(event, "block_id"))
        colors.append(STATE_COLORS.get(state_name, "#94a3b8"))
        texts.append(
            f"{event.get('event')}<br>"
            f"block={event.get('block_id')}<br>"
            f"state={state_name}<br>"
            f"retain={_float(event, 'retain_score'):.1f}"
        )
    fig = go.Figure(
        data=go.Scattergl(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(size=4, color=colors, opacity=0.85),
            text=texts,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="elapsed seconds",
        yaxis_title="KV block id",
        paper_bgcolor="#0b1020",
        plot_bgcolor="#0b1020",
        font=dict(color="#e5e7eb"),
        height=420,
        margin=dict(l=40, r=20, t=55, b=40),
    )
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.18)")
    fig.update_yaxes(gridcolor="rgba(148, 163, 184, 0.12)")
    return fig

