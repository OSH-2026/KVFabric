#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


POLICIES = ("lru", "shared_aware", "family_protect")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def read_jsonl(path: Path, limit: int | None = None) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    bad_lines = 0
    with path.open("rb") as handle:
        if limit is not None and limit > 0:
            handle.seek(0, 2)
            size = handle.tell()
            window = max(1 << 20, min(64 << 20, limit * 1024))
            offset = max(size - window, 0)
            handle.seek(offset)
            raw_lines = handle.read().splitlines()
            if offset > 0 and raw_lines:
                raw_lines = raw_lines[1:]
            raw_lines = raw_lines[-limit:]
        else:
            raw_lines = handle.read().splitlines()
    for raw in raw_lines:
        if not raw.strip(b"\x00 \t\r\n"):
            continue
        try:
            text = raw.replace(b"\x00", b"").decode("utf-8", errors="replace")
            text = text.strip()
            if text:
                rows.append(json.loads(text))
        except Exception:
            bad_lines += 1
    return rows, bad_lines


def newest_mtime(paths: list[Path]) -> float:
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    return max(mtimes) if mtimes else 0.0


def parse_prometheus_lines(lines: list[str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([-+0-9.eE]+)", line)
        if not match:
            continue
        name, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        short_name = name.split(":", 1)[-1]
        metrics[short_name] = value
    return metrics


def last_prometheus_metrics(path: Path) -> tuple[dict[str, float], dict[str, Any]]:
    rows, _ = read_jsonl(path, limit=1)
    if not rows:
        return {}, {}
    row = rows[-1]
    lines = row.get("lines") or []
    if not isinstance(lines, list):
        return {}, row
    return parse_prometheus_lines([str(line) for line in lines]), row


def format_age(timestamp: float) -> str:
    if timestamp <= 0:
        return "unknown"
    age = max(time.time() - timestamp, 0.0)
    if age < 60:
        return f"{age:.0f}s ago"
    if age < 3600:
        return f"{age / 60:.1f}m ago"
    return f"{age / 3600:.1f}h ago"


@dataclass
class PolicySnapshot:
    policy: str
    policy_dir: Path
    state: dict[str, Any]
    heartbeat: dict[str, Any]
    rolling: list[dict[str, Any]]
    rolling_bad_lines: int
    class_rolling: list[dict[str, Any]]
    prometheus: dict[str, float]
    prometheus_raw: dict[str, Any]
    lifecycle_metrics: dict[str, Any]
    final_metrics: dict[str, Any]
    class_metrics: dict[str, Any]
    raw_outputs: list[dict[str, Any]]
    raw_outputs_bad_lines: int
    lifecycle_path: Path

    @property
    def exists(self) -> bool:
        return self.policy_dir.exists()

    @property
    def latest_rolling(self) -> dict[str, Any]:
        return self.rolling[-1] if self.rolling else {}

    @property
    def latest_class_rolling(self) -> dict[str, Any]:
        return self.class_rolling[-1] if self.class_rolling else {}

    @property
    def last_update_mtime(self) -> float:
        paths = [
            self.policy_dir / "policy_state.json",
            self.policy_dir / "heartbeat.json",
            self.policy_dir / "online_trace" / "rolling_metrics.jsonl",
            self.policy_dir / "online_trace" / "prometheus_cache_samples.jsonl",
            self.policy_dir / "kvfabric_lifecycle.jsonl",
        ]
        return newest_mtime(paths)

    @property
    def inferred_status(self) -> str:
        status = str(self.state.get("status") or "").lower()
        if status:
            return status
        if self.final_metrics:
            return "completed"
        if self.rolling:
            if time.time() - self.last_update_mtime > 180:
                return "stalled"
            return "running"
        if self.exists:
            return "started"
        return "pending"


class KVFabricRunReader:
    def __init__(self, run_root: Path, job_log: Path | None = None) -> None:
        self.run_root = run_root.expanduser().resolve()
        self.job_log = job_log.expanduser().resolve() if job_log else None
        self._trace_index: dict[str, dict[str, Any]] | None = None

    @classmethod
    def latest(cls, runs_dir: Path, job_log: Path | None = None) -> "KVFabricRunReader":
        candidates = sorted(
            [path for path in runs_dir.expanduser().glob("*") if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
        )
        if not candidates:
            raise FileNotFoundError(f"No runs under {runs_dir}")
        return cls(candidates[-1], job_log=job_log)

    def run_state(self) -> dict[str, Any]:
        return load_json(self.run_root / "run_state.json")

    def trace_summary(self) -> dict[str, Any]:
        return load_json(self.run_root / "trace" / "trace_summary.json")

    def job_log_tail(self, max_bytes: int = 30000) -> str:
        if self.job_log is None or not self.job_log.exists():
            return ""
        with self.job_log.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(size - max_bytes, 0))
            data = handle.read()
        return data.replace(b"\x00", b"").decode("utf-8", errors="replace")

    def load_trace_index(self) -> dict[str, dict[str, Any]]:
        if self._trace_index is not None:
            return self._trace_index
        trace_path = self.run_root / "trace" / "trace.jsonl"
        rows, _ = read_jsonl(trace_path)
        self._trace_index = {
            str(row.get("request_id")): row
            for row in rows
            if row.get("request_id") is not None
        }
        return self._trace_index

    def prompt_excerpt(self, request_id: str, limit: int = 1600) -> dict[str, Any]:
        entry = self.load_trace_index().get(request_id)
        if not entry:
            return {}
        prompt_ref = entry.get("prompt_ref")
        if not prompt_ref:
            return {}
        prompt_path = self.run_root / "trace" / str(prompt_ref)
        data = load_json(prompt_path)
        messages = data.get("messages") or []
        text = "\n".join(
            f"{message.get('role', 'unknown')}: {message.get('content', '')}"
            for message in messages
            if isinstance(message, dict)
        )
        return {
            "request_id": request_id,
            "prompt_ref": prompt_ref,
            "prompt_chars": len(text),
            "prompt_message_count": len(messages),
            "prompt_excerpt": text[:limit],
            **entry,
        }

    def policy_snapshot(
        self,
        policy: str,
        rolling_limit: int = 2048,
        output_limit: int = 200,
    ) -> PolicySnapshot:
        policy_dir = self.run_root / policy
        online_dir = policy_dir / "online_trace"
        if not online_dir.exists():
            online_dir = policy_dir / "online_duration"
        rolling, rolling_bad = read_jsonl(
            online_dir / "rolling_metrics.jsonl",
            limit=rolling_limit,
        )
        class_rolling, _ = read_jsonl(
            online_dir / "rolling_class_metrics.jsonl",
            limit=rolling_limit,
        )
        raw_outputs, raw_bad = read_jsonl(
            online_dir / "raw_outputs_sample.jsonl",
            limit=output_limit,
        )
        prometheus, prometheus_raw = last_prometheus_metrics(
            online_dir / "prometheus_cache_samples.jsonl"
        )
        return PolicySnapshot(
            policy=policy,
            policy_dir=policy_dir,
            state=load_json(policy_dir / "policy_state.json"),
            heartbeat=load_json(policy_dir / "heartbeat.json"),
            rolling=rolling,
            rolling_bad_lines=rolling_bad,
            class_rolling=class_rolling,
            prometheus=prometheus,
            prometheus_raw=prometheus_raw,
            lifecycle_metrics=load_json(policy_dir / "kvfabric_lifecycle_metrics.json"),
            final_metrics=load_json(online_dir / "metrics.json"),
            class_metrics=load_json(online_dir / "class_metrics.json"),
            raw_outputs=raw_outputs,
            raw_outputs_bad_lines=raw_bad,
            lifecycle_path=policy_dir / "kvfabric_lifecycle.jsonl",
        )

    def policy_snapshots(self) -> list[PolicySnapshot]:
        return [self.policy_snapshot(policy) for policy in POLICIES]

    def current_policy(self) -> str:
        run_state = self.run_state()
        current = run_state.get("current_policy")
        if current:
            return str(current)
        snapshots = self.policy_snapshots()
        running = [
            snapshot
            for snapshot in snapshots
            if snapshot.inferred_status in {"running", "started"}
        ]
        if running:
            return running[-1].policy
        existing = [snapshot for snapshot in snapshots if snapshot.exists]
        return existing[-1].policy if existing else POLICIES[0]
