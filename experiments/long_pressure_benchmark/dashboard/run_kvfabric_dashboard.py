#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st
    from streamlit.components.v1 import html as st_html
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "KVFabric dashboard requires streamlit, pandas and plotly in the runtime."
    ) from exc

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from kv_cache_replay import (  # noqa: E402
    STATE_COLORS,
    load_replay_state,
    make_block_grid_figure,
    make_event_timeline_figure,
)
from kvfabric_run_reader import (  # noqa: E402
    KVFabricRunReader,
    POLICIES,
    PolicySnapshot,
    format_age,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KVFabric long benchmark dashboard.")
    parser.add_argument("--run-root", default="")
    parser.add_argument(
        "--runs-dir",
        default="experiments/long_pressure_benchmark/runs",
    )
    parser.add_argument("--job-log", default="")
    parser.add_argument("--refresh-seconds", type=float, default=5.0)
    parser.add_argument("--lifecycle-event-limit", type=int, default=100000)
    args, _ = parser.parse_known_args()
    return args


def number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        if isinstance(value, int):
            return f"{value:,}"
        return f"{float(value):,.{digits}f}"
    except Exception:
        return str(value)


def percent(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "n/a"


def metric_value(snapshot: PolicySnapshot, key: str, default: Any = None) -> Any:
    if snapshot.final_metrics and key in snapshot.final_metrics:
        return snapshot.final_metrics.get(key)
    return snapshot.latest_rolling.get(key, default)


def configure_page() -> None:
    st.set_page_config(
        page_title="KVFabric Live Benchmark",
        layout="wide",
        page_icon="KV",
    )
    st.markdown(
        """
        <style>
        .stApp {
            background: #0b1020;
            color: #e5e7eb;
        }
        div[data-testid="stMetric"] {
            background: rgba(15, 23, 42, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 10px;
            padding: 0.65rem 0.8rem;
            box-shadow: 0 12px 28px rgba(0,0,0,0.22);
        }
        div[data-testid="stMetricLabel"] {
            color: #cbd5e1;
            font-weight: 650;
        }
        .kv-panel {
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 10px;
            padding: 0.85rem;
        }
        .status-running { color: #22c55e; font-weight: 700; }
        .status-stalled { color: #f59e0b; font-weight: 700; }
        .status-failed { color: #ef4444; font-weight: 700; }
        .status-pending { color: #94a3b8; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_class(status: str) -> str:
    if status in {"completed", "running"}:
        return "status-running"
    if status in {"failed", "error"}:
        return "status-failed"
    if status in {"stalled", "started"}:
        return "status-stalled"
    return "status-pending"


def rolling_dataframe(snapshot: PolicySnapshot) -> pd.DataFrame:
    if not snapshot.rolling:
        return pd.DataFrame()
    return pd.DataFrame(snapshot.rolling)


def plot_rolling(snapshot: PolicySnapshot) -> go.Figure:
    df = rolling_dataframe(snapshot)
    fig = go.Figure()
    if df.empty:
        return fig
    x = df.get("elapsed_seconds", pd.Series(range(len(df))))
    for column, color, label in [
        ("total_tokens_per_second", "#38bdf8", "tok/s"),
        ("goodput_total_tokens_per_second", "#22c55e", "goodput tok/s"),
        ("latency_p95_seconds", "#f59e0b", "p95 latency"),
        ("latency_avg_seconds", "#a78bfa", "avg latency"),
    ]:
        if column in df:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=df[column],
                    mode="lines",
                    name=label,
                    line=dict(color=color, width=2),
                )
            )
    fig.update_layout(
        paper_bgcolor="#0b1020",
        plot_bgcolor="#0b1020",
        font=dict(color="#e5e7eb"),
        margin=dict(l=35, r=20, t=35, b=35),
        height=360,
        legend=dict(orientation="h"),
    )
    fig.update_xaxes(title="elapsed seconds", gridcolor="rgba(148,163,184,0.16)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.12)")
    return fig


def plot_class_latency(snapshot: PolicySnapshot) -> go.Figure:
    data = snapshot.latest_class_rolling.get("classes") or {}
    fig = go.Figure()
    if not isinstance(data, dict) or not data:
        data = snapshot.class_metrics or {}
    if not data:
        return fig
    rows = []
    for request_class, metrics in data.items():
        if not isinstance(metrics, dict):
            continue
        rows.append(
            {
                "class": request_class,
                "p95": metrics.get("latency_p95_seconds", 0.0),
                "avg": metrics.get("latency_avg_seconds", 0.0),
                "completed": metrics.get("completed", 0),
            }
        )
    rows.sort(key=lambda row: float(row["p95"] or 0.0), reverse=True)
    labels = [row["class"] for row in rows]
    fig.add_trace(
        go.Bar(
            x=[row["p95"] for row in rows],
            y=labels,
            orientation="h",
            marker_color="#f59e0b",
            name="p95",
            text=[f"n={int(row['completed'] or 0)}" for row in rows],
        )
    )
    fig.add_trace(
        go.Bar(
            x=[row["avg"] for row in rows],
            y=labels,
            orientation="h",
            marker_color="#38bdf8",
            name="avg",
        )
    )
    fig.update_layout(
        paper_bgcolor="#0b1020",
        plot_bgcolor="#0b1020",
        font=dict(color="#e5e7eb"),
        barmode="group",
        margin=dict(l=20, r=20, t=35, b=35),
        height=360,
    )
    fig.update_xaxes(title="seconds", gridcolor="rgba(148,163,184,0.16)")
    fig.update_yaxes(autorange="reversed")
    return fig


def render_top_metrics(reader: KVFabricRunReader, snapshot: PolicySnapshot) -> None:
    trace = reader.trace_summary()
    run_state = reader.run_state()
    cols = st.columns(6)
    cols[0].metric("Policy", snapshot.policy)
    cols[1].metric("Status", snapshot.inferred_status)
    cols[2].metric(
        "Completed",
        number(metric_value(snapshot, "completed", metric_value(snapshot, "requests", 0)), 0),
        f"trace {number(trace.get('requests'), 0)}",
    )
    cols[3].metric(
        "Total tok/s",
        number(metric_value(snapshot, "total_tokens_per_second", 0.0), 2),
    )
    cols[4].metric(
        "P95 latency",
        number(metric_value(snapshot, "latency_p95_seconds", 0.0), 2) + "s",
    )
    cols[5].metric(
        "KV usage",
        percent(snapshot.prometheus.get("kv_cache_usage_perc"), 1),
        f"updated {format_age(snapshot.last_update_mtime)}",
    )
    st.caption(
        f"Run: `{reader.run_root}` | phase: "
        f"`{run_state.get('phase', 'unknown')}` | "
        f"message: `{run_state.get('message', '')}`"
    )


def render_policy_timeline(snapshots: list[PolicySnapshot]) -> None:
    rows = []
    for snapshot in snapshots:
        rows.append(
            {
                "policy": snapshot.policy,
                "status": snapshot.inferred_status,
                "phase": snapshot.state.get("phase", "unknown"),
                "last_update": format_age(snapshot.last_update_mtime),
                "rolling_rows": len(snapshot.rolling),
                "final_metrics": bool(snapshot.final_metrics),
                "lifecycle_metrics": bool(snapshot.lifecycle_metrics),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_request_samples(reader: KVFabricRunReader, snapshot: PolicySnapshot) -> None:
    samples = list(reversed(snapshot.raw_outputs[-20:]))
    if not samples:
        st.info("No sampled outputs yet. Increase TRACE_BENCH_RAW_SAMPLE_RATE for demos.")
        trace_index = reader.load_trace_index()
        if trace_index:
            first_key = next(iter(trace_index))
            prompt = reader.prompt_excerpt(first_key)
            st.markdown("**Trace prompt preview**")
            st.json(
                {
                    key: prompt.get(key)
                    for key in [
                        "request_id",
                        "request_class",
                        "tenant_id",
                        "family_id",
                        "turn_index",
                        "prompt_chars",
                        "prompt_excerpt",
                    ]
                }
            )
        return
    for sample in samples[:8]:
        title = (
            f"{sample.get('request_id')} | {sample.get('request_class')} | "
            f"{number(sample.get('latency_seconds'), 2)}s"
        )
        with st.expander(title):
            left, right = st.columns(2)
            left.json(
                {
                    key: sample.get(key)
                    for key in [
                        "tenant_id",
                        "family_id",
                        "session_id",
                        "turn_index",
                        "expected_reuse",
                        "cache_priority",
                        "prompt_chars",
                        "usage",
                    ]
                }
            )
            right.markdown("**Prompt excerpt**")
            right.text(sample.get("prompt_excerpt", ""))
            st.markdown("**Output / Error**")
            st.text(sample.get("output") or sample.get("error") or "")


def render_lifecycle_numbers(state: Any, snapshot: PolicySnapshot) -> None:
    lifecycle = snapshot.lifecycle_metrics or {}
    counters = state.counters
    cols = st.columns(6)
    cols[0].metric(
        "Prefix hit",
        percent(lifecycle.get("prefix_hit_rate", state.prefix_hit_rate), 2),
        number(lifecycle.get("prefix_hit_tokens", counters["prefix_hit_tokens"]), 0),
    )
    cols[1].metric(
        "Evicted",
        number(lifecycle.get("evicted_blocks", counters["evicted_blocks"]), 0),
    )
    cols[2].metric(
        "Rebuilt",
        number(
            lifecycle.get(
                "rebuilt_from_eviction_blocks",
                counters["rebuilt_from_eviction"],
            ),
            0,
        ),
    )
    cols[3].metric(
        "Admission saved",
        number(
            lifecycle.get(
                "cache_admission_saved_blocks",
                counters["admission_saved_blocks"],
            ),
            0,
        ),
    )
    cols[4].metric(
        "Defers",
        number(
            lifecycle.get("request_deferred_events", counters["scheduler_defers"]),
            0,
        ),
    )
    cols[5].metric(
        "Latency promotes",
        number(
            lifecycle.get(
                "request_latency_promoted_events",
                counters["scheduler_latency_promotes"],
            ),
            0,
        ),
    )


def render_dashboard(reader: KVFabricRunReader, args: argparse.Namespace) -> None:
    snapshots = reader.policy_snapshots()
    current_policy = reader.current_policy()
    selected_policy = st.sidebar.radio(
        "Policy",
        POLICIES,
        index=POLICIES.index(current_policy) if current_policy in POLICIES else 0,
    )
    snapshot = next(item for item in snapshots if item.policy == selected_policy)

    render_top_metrics(reader, snapshot)
    tab_live, tab_replay, tab_requests, tab_compare, tab_logs = st.tabs(
        ["Live Overview", "KV Cache Replay", "Requests", "Policy Compare", "Logs"]
    )

    with tab_live:
        left, right = st.columns([1.2, 1.0])
        with left:
            st.subheader("Policy Timeline")
            render_policy_timeline(snapshots)
            st.subheader("Rolling Metrics")
            st.plotly_chart(plot_rolling(snapshot), use_container_width=True)
        with right:
            st.subheader("Class Latency")
            st.plotly_chart(plot_class_latency(snapshot), use_container_width=True)
            st.subheader("Prometheus Snapshot")
            st.json(snapshot.prometheus)

    with tab_replay:
        state = load_replay_state(
            snapshot.lifecycle_path,
            limit_events=args.lifecycle_event_limit,
        )
        render_lifecycle_numbers(state, snapshot)
        left, right = st.columns([1.2, 1.0])
        with left:
            st.plotly_chart(
                make_block_grid_figure(state, title=f"{selected_policy} KV block grid"),
                use_container_width=True,
            )
        with right:
            st.markdown("**Current request**")
            st.json(state.current_request)
            st.markdown("**Replay counters**")
            st.json({**state.counters, "bad_lines": state.bad_lines})
        st.plotly_chart(
            make_event_timeline_figure(
                snapshot.lifecycle_path,
                limit_events=min(args.lifecycle_event_limit, 20000),
                title=f"{selected_policy} lifecycle timeline",
            ),
            use_container_width=True,
        )
        st.caption("State colors: " + ", ".join(f"{k} {v}" for k, v in STATE_COLORS.items()))

    with tab_requests:
        render_request_samples(reader, snapshot)

    with tab_compare:
        rows = []
        for item in snapshots:
            rows.append(
                {
                    "policy": item.policy,
                    "status": item.inferred_status,
                    "completed": metric_value(item, "completed", metric_value(item, "requests", 0)),
                    "tok/s": metric_value(item, "total_tokens_per_second", 0.0),
                    "goodput tok/s": metric_value(
                        item,
                        "goodput_total_tokens_per_second",
                        0.0,
                    ),
                    "avg latency": metric_value(item, "latency_avg_seconds", 0.0),
                    "p95 latency": metric_value(item, "latency_p95_seconds", 0.0),
                    "prefix hit rate": item.lifecycle_metrics.get("prefix_hit_rate"),
                    "rebuilt": item.lifecycle_metrics.get(
                        "rebuilt_from_eviction_blocks"
                    ),
                    "admission saved": item.lifecycle_metrics.get(
                        "cache_admission_saved_blocks"
                    ),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_logs:
        st.subheader("Job Log Tail")
        st.code(reader.job_log_tail(), language="text")
        st.subheader("Run State")
        st.json(reader.run_state())
        st.subheader("Policy State")
        st.json(snapshot.state)


def main() -> None:
    args = parse_args()
    configure_page()
    run_root = Path(args.run_root) if args.run_root else None
    job_log = Path(args.job_log) if args.job_log else None
    try:
        reader = (
            KVFabricRunReader(run_root, job_log=job_log)
            if run_root
            else KVFabricRunReader.latest(Path(args.runs_dir), job_log=job_log)
        )
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    render_dashboard(reader, args)
    if args.refresh_seconds > 0:
        st_html(
            (
                "<script>"
                f"setTimeout(() => window.parent.location.reload(), {int(args.refresh_seconds * 1000)});"
                "</script>"
            ),
            height=0,
        )


if __name__ == "__main__":
    main()
