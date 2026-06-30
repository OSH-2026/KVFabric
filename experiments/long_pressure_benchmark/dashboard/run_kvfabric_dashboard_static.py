#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from kv_cache_replay import load_replay_state  # noqa: E402
from kvfabric_run_reader import KVFabricRunReader  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dependency-free KVFabric dashboard fallback."
    )
    parser.add_argument("--run-root", default="")
    parser.add_argument("--runs-dir", default="experiments/long_pressure_benchmark/runs")
    parser.add_argument("--job-log", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--refresh-seconds", type=float, default=5.0)
    parser.add_argument("--lifecycle-event-limit", type=int, default=12000)
    return parser.parse_args()


def metric(snapshot: Any, key: str, default: Any = None) -> Any:
    if snapshot.final_metrics and key in snapshot.final_metrics:
        return snapshot.final_metrics.get(key)
    return snapshot.latest_rolling.get(key, default)


def metric_first(snapshot: Any, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = metric(snapshot, key, None)
        if value is not None:
            return value
    return default


def newest_run(runs_dir: Path) -> Path:
    candidates = [path for path in runs_dir.expanduser().glob("*") if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No runs under {runs_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def compact_blocks(run_root: Path, policy: str, limit_events: int) -> dict[str, Any]:
    lifecycle_path = run_root / policy / "kvfabric_lifecycle.jsonl"
    if not lifecycle_path.exists():
        return {
            "available": False,
            "message": f"missing {lifecycle_path.name}",
            "blocks": [],
            "counters": {},
            "current_request": {},
        }
    state = load_replay_state(lifecycle_path, limit_events=limit_events)
    blocks = []
    for block in sorted(state.blocks.values(), key=lambda item: item.block_id)[:768]:
        blocks.append(
            {
                "id": block.block_id,
                "state": block.display_state(),
                "hit_count": block.hit_count,
                "share_degree": block.share_degree,
                "retain_score": block.retain_score,
                "family_id": block.family_id,
            }
        )
    return {
        "available": True,
        "elapsed_seconds": state.elapsed_seconds,
        "prefix_hit_rate": state.prefix_hit_rate,
        "bad_lines": state.bad_lines,
        "block_count": len(blocks),
        "blocks": blocks,
        "counters": dict(state.counters),
        "current_request": state.current_request,
    }


def build_snapshot(args: argparse.Namespace, query: dict[str, list[str]]) -> dict[str, Any]:
    run_root = Path(args.run_root).expanduser() if args.run_root else newest_run(
        Path(args.runs_dir)
    )
    job_log = Path(args.job_log).expanduser() if args.job_log else None
    reader = KVFabricRunReader(run_root, job_log=job_log)
    policy_names = reader.policy_names()
    current_policy = query.get("policy", [reader.current_policy()])[0]
    if current_policy not in policy_names:
        current_policy = reader.current_policy()
    snapshots = reader.policy_snapshots()
    policy_rows = []
    for item in snapshots:
        completed = metric_first(item, ("completed", "requests"), 0)
        offered = metric_first(
            item,
            ("offered", "offered_requests", "measured_offered"),
            completed,
        )
        policy_rows.append(
            {
                "policy": item.policy,
                "status": item.inferred_status,
                "completed": completed,
                "offered": offered,
                "tok_s": metric(item, "total_tokens_per_second", 0.0),
                "goodput_tok_s": metric(item, "goodput_total_tokens_per_second", 0.0),
                "e2e_goodput_tok_s": metric(
                    item,
                    "e2e_goodput_total_tokens_per_second",
                    0.0,
                ),
                "avg_latency_s": metric(item, "latency_avg_seconds", None),
                "p50_latency_s": metric(item, "latency_p50_seconds", None),
                "p95_latency_s": metric(item, "latency_p95_seconds", None),
                "p99_latency_s": metric(item, "latency_p99_seconds", None),
                "e2e_p50_latency_s": metric(item, "e2e_latency_p50_seconds", None),
                "e2e_p95_latency_s": metric(item, "e2e_latency_p95_seconds", None),
                "e2e_p99_latency_s": metric(item, "e2e_latency_p99_seconds", None),
                "slo_miss_rate": metric(item, "slo_miss_rate", None),
                "e2e_slo_miss_rate": metric(item, "e2e_slo_miss_rate", None),
                "prefix_hit_rate": item.lifecycle_metrics.get("prefix_hit_rate"),
                "rebuilt": item.lifecycle_metrics.get("rebuilt_from_eviction_blocks"),
                "admission_saved": item.lifecycle_metrics.get(
                    "cache_admission_saved_blocks"
                ),
                "rolling": item.rolling[-240:],
                "last_update_epoch": item.last_update_mtime,
                "has_data": bool(
                    item.rolling
                    or item.final_metrics
                    or item.lifecycle_metrics
                    or completed
                ),
            }
        )
    selected = next(
        (item for item in snapshots if item.policy == current_policy),
        snapshots[-1],
    )
    replay = compact_blocks(
        run_root,
        current_policy,
        limit_events=max(args.lifecycle_event_limit, 1),
    )
    replay_counters = replay.get("counters") or {}
    for row in policy_rows:
        if row["policy"] != current_policy:
            continue
        if row["prefix_hit_rate"] is None and replay.get("available"):
            row["prefix_hit_rate"] = replay.get("prefix_hit_rate")
        if row["rebuilt"] is None:
            row["rebuilt"] = replay_counters.get("rebuilt_from_eviction")
        if row["admission_saved"] is None:
            row["admission_saved"] = replay_counters.get("admission_saved_blocks")
        break
    return {
        "generated_at": time.time(),
        "dashboard_backend": "static",
        "run_root": str(run_root.resolve()),
        "run_name": run_root.name,
        "run_state": reader.run_state(),
        "trace_summary": reader.trace_summary(),
        "current_policy": current_policy,
        "policies": policy_rows,
        "class_metrics": selected.latest_class_rolling.get("classes")
        or selected.class_metrics,
        "prometheus": selected.prometheus,
        "raw_outputs": selected.raw_outputs[-20:],
        "job_log_tail": reader.job_log_tail(max_bytes=18000),
        "replay": replay,
    }


HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>KVFabric Live Benchmark</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: rgba(15, 23, 42, 0.82);
      --line: rgba(148, 163, 184, 0.2);
      --text: #e5e7eb;
      --muted: #94a3b8;
      --green: #22c55e;
      --cyan: #38bdf8;
      --amber: #f59e0b;
      --red: #ef4444;
      --violet: #a855f7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      letter-spacing: 0;
    }
    header {
      padding: 18px 22px 10px;
      border-bottom: 1px solid var(--line);
      background: rgba(2, 6, 23, 0.92);
      z-index: 5;
    }
    h1 { margin: 0; font-size: 24px; font-weight: 760; }
    .sub { color: var(--muted); margin-top: 6px; font-size: 13px; overflow-wrap: anywhere; }
    main { padding: 18px 22px 28px; }
    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(6, minmax(140px, 1fr)); }
    .cols { grid-template-columns: 1.35fr 1fr; align-items: start; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.24);
    }
    .card .label { color: var(--muted); font-size: 12px; font-weight: 700; }
    .card .value { font-size: 24px; font-weight: 780; margin-top: 7px; }
    .card .hint { color: var(--muted); font-size: 12px; margin-top: 5px; }
    .tabs { display: flex; gap: 8px; margin: 14px 0; flex-wrap: wrap; }
    button {
      background: #111827;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 11px;
      cursor: pointer;
      font-weight: 650;
    }
    button.active { background: #0f766e; border-color: #2dd4bf; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px 7px; border-bottom: 1px solid rgba(148,163,184,0.12); text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    th { color: #cbd5e1; font-size: 12px; }
    .muted-cell { color: var(--muted); text-align: left; }
    .status-completed { color: var(--green); font-weight: 780; }
    .status-running { color: var(--cyan); font-weight: 780; }
    .status-stalled, .status-started { color: var(--amber); font-weight: 780; }
    .status-failed { color: var(--red); font-weight: 780; }
    canvas { width: 100%; background: rgba(2,6,23,0.35); border-radius: 8px; border: 1px solid rgba(148,163,184,0.12); }
    #blockGrid { display: grid; gap: 3px; grid-template-columns: repeat(auto-fill, minmax(12px, 1fr)); }
    .block { aspect-ratio: 1; border-radius: 3px; opacity: 0.9; border: 1px solid rgba(255,255,255,0.08); }
    .legend { display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-top: 9px; }
    .dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; margin-right: 4px; }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: #cbd5e1;
      background: rgba(2,6,23,0.45);
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 8px;
      padding: 12px;
      max-height: 360px;
      overflow: auto;
    }
    @media (max-width: 1100px) {
      .cards { grid-template-columns: repeat(2, minmax(130px, 1fr)); }
      .cols { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>KVFabric Live Benchmark</h1>
    <div class="sub" id="runLine">Loading...</div>
  </header>
  <main class="grid">
    <section class="grid cards" id="cards"></section>
    <section class="panel">
      <div class="tabs" id="policyTabs"></div>
      <table id="policyTable"></table>
    </section>
    <section class="grid cols">
      <div class="panel">
        <h3>Rolling Goodput / Latency</h3>
        <canvas id="rollingChart" height="260"></canvas>
      </div>
      <div class="panel">
        <h3>KV Cache Replay</h3>
        <div id="replayMeta" class="sub"></div>
        <div id="blockGrid"></div>
        <div class="legend" id="legend"></div>
      </div>
    </section>
    <section class="panel">
      <h3>Request Class Latency</h3>
      <table id="classTable"></table>
    </section>
    <section class="grid cols">
      <div class="panel">
        <h3>Recent Samples</h3>
        <pre id="samples"></pre>
      </div>
      <div class="panel">
        <h3>Job Log Tail</h3>
        <pre id="log"></pre>
      </div>
    </section>
  </main>
  <script>
    const refreshMs = __REFRESH_MS__;
    const snapshotMode = new URLSearchParams(location.search).get("snapshot") === "1";
    let currentPolicy = "";
    const colors = {
      FREE: "#1f2937", ACTIVE: "#2563eb", SEALED: "#06b6d4",
      SHARED: "#22c55e", COOLING_WARM: "#eab308",
      COOLING_HOT: "#f97316", EVICTED: "#ef4444", REBUILT: "#a855f7"
    };
    const finite = (v) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v));
    const fmt = (v, d=2) => finite(v) ? Number(v).toLocaleString(undefined, {maximumFractionDigits:d}) : "n/a";
    const sec = (v) => finite(v) ? `${fmt(v)}s` : "n/a";
    const pct = (v) => finite(v) ? `${fmt(Number(v) * 100)}%` : "n/a";
    const firstFinite = (...values) => values.find(v => finite(v));
    function card(label, value, hint="") {
      return `<div class="panel card"><div class="label">${label}</div><div class="value">${value}</div><div class="hint">${hint}</div></div>`;
    }
    function stateClass(status) { return `status-${String(status || "pending").toLowerCase()}`; }
    async function load() {
      const url = currentPolicy ? `/api/snapshot?policy=${encodeURIComponent(currentPolicy)}` : "/api/snapshot";
      const data = await (await fetch(url, {cache: "no-store"})).json();
      currentPolicy = data.current_policy;
      render(data);
    }
    function render(data) {
      const selected = data.policies.find(p => p.policy === data.current_policy) || data.policies[data.policies.length - 1] || {};
      const primaryGoodput = firstFinite(selected.e2e_goodput_tok_s, selected.goodput_tok_s, selected.tok_s, 0);
      const primaryP95 = firstFinite(selected.e2e_p95_latency_s, selected.p95_latency_s);
      const primaryTail = firstFinite(
        selected.e2e_p99_latency_s,
        selected.p99_latency_s,
        selected.e2e_p95_latency_s,
        selected.p95_latency_s
      );
      const tailLabel = finite(selected.e2e_p99_latency_s) || finite(selected.p99_latency_s) ? "P99" : "P95";
      document.getElementById("runLine").textContent = `${data.run_name} | ${data.run_root}`;
      document.getElementById("cards").innerHTML = [
        card("Policy", data.current_policy, selected.status || ""),
        card("Completed", fmt(selected.completed, 0), `offered ${fmt(selected.offered, 0)}`),
        card("SLO goodput", fmt(primaryGoodput), `raw tok/s ${fmt(selected.tok_s)}`),
        card("E2E / service p95", sec(primaryP95), `service ${sec(selected.p95_latency_s)}`),
        card(`${tailLabel} / SLO miss`, sec(primaryTail), `miss ${pct(selected.e2e_slo_miss_rate ?? selected.slo_miss_rate)}`),
        card("Prefix hit", selected.prefix_hit_rate == null ? "n/a" : `${fmt(selected.prefix_hit_rate * 100)}%`, `rebuilt ${fmt(selected.rebuilt, 0)}`),
        card("KV usage", `${fmt((data.prometheus.kv_cache_usage_perc || 0) * 100)}%`, `waiting ${fmt(data.prometheus.num_requests_waiting || 0, 0)}`)
      ].join("");
      document.getElementById("policyTabs").innerHTML = data.policies.map(p =>
        `<button class="${p.policy === data.current_policy ? "active" : ""}" onclick="currentPolicy='${p.policy}'; load();">${p.policy}</button>`
      ).join("");
      document.getElementById("policyTable").innerHTML =
        `<tr><th>policy</th><th>status</th><th>completed</th><th>SLO goodput</th><th>e2e p95</th><th>svc p95</th><th>SLO miss</th><th>hit</th><th>rebuilt</th><th>saved</th></tr>` +
        data.policies.map(policyRow).join("");
      drawChart(selected.rolling || []);
      renderReplay(data.replay || {});
      renderClassTable(data.class_metrics || {});
      document.getElementById("samples").textContent = JSON.stringify(data.raw_outputs || [], null, 2);
      document.getElementById("log").textContent = data.job_log_tail || "";
    }
    function policyRow(p) {
      const waiting = !p.has_data && Number(p.completed || 0) === 0;
      if (waiting) {
        return `<tr><td>${p.policy}</td><td class="${stateClass(p.status)}">${p.status}</td><td>${fmt(p.completed,0)}</td><td colspan="7" class="muted-cell">waiting for this policy to start</td></tr>`;
      }
      return `<tr><td>${p.policy}</td><td class="${stateClass(p.status)}">${p.status}</td><td>${fmt(p.completed,0)}</td><td>${fmt(firstFinite(p.e2e_goodput_tok_s, p.goodput_tok_s))}</td><td>${sec(p.e2e_p95_latency_s)}</td><td>${sec(p.p95_latency_s)}</td><td>${pct(p.e2e_slo_miss_rate ?? p.slo_miss_rate)}</td><td>${p.prefix_hit_rate == null ? "n/a" : fmt(p.prefix_hit_rate*100)+"%"}</td><td>${fmt(p.rebuilt,0)}</td><td>${fmt(p.admission_saved,0)}</td></tr>`;
    }
    function drawChart(rows) {
      const canvas = document.getElementById("rollingChart");
      const ctx = canvas.getContext("2d");
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(600, rect.width * devicePixelRatio);
      canvas.height = 260 * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      ctx.clearRect(0,0,rect.width,260);
      ctx.strokeStyle = "rgba(148,163,184,.18)";
      ctx.lineWidth = 1;
      for (let i=0;i<5;i++) { const y=30+i*44; ctx.beginPath(); ctx.moveTo(45,y); ctx.lineTo(rect.width-15,y); ctx.stroke(); }
      if (!rows.length) return;
      const maxX = Math.max(...rows.map(r => Number(r.elapsed_seconds || 0)), 1);
      const series = [
        ["goodput_total_tokens_per_second", "#22c55e", "goodput"],
        ["e2e_goodput_total_tokens_per_second", "#38bdf8", "e2e goodput"],
        ["latency_p95_seconds", "#f59e0b", "svc p95"],
        ["e2e_latency_p95_seconds", "#a855f7", "e2e p95"]
      ];
      const maxY = Math.max(...rows.flatMap(r => series.map(s => Number(r[s[0]] || 0))), 1);
      series.forEach(([key, color]) => {
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
        rows.forEach((r, idx) => {
          const x = 45 + (Number(r.elapsed_seconds || 0) / maxX) * (rect.width - 70);
          const y = 230 - (Number(r[key] || 0) / maxY) * 190;
          if (idx === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
        });
        ctx.stroke();
      });
      ctx.fillStyle = "#cbd5e1"; ctx.font = "12px sans-serif";
      ctx.fillText(`max ${fmt(maxY)}`, 45, 20);
      series.forEach(([_, color, name], i) => { ctx.fillStyle = color; ctx.fillText(name, 120 + i*80, 20); });
    }
    function renderClassTable(classes) {
      const rows = Object.entries(classes || {}).map(([name, m]) => ({
        name,
        completed: Number(m.completed || 0),
        goodput: firstFinite(m.e2e_goodput_total_tokens_per_second, m.goodput_total_tokens_per_second, 0),
        p95: firstFinite(m.e2e_latency_p95_seconds, m.latency_p95_seconds),
        svcP95: firstFinite(m.latency_p95_seconds),
        miss: firstFinite(m.e2e_slo_miss_rate, m.slo_miss_rate),
      })).sort((a, b) => Number(b.p95 || -1) - Number(a.p95 || -1)).slice(0, 10);
      document.getElementById("classTable").innerHTML =
        `<tr><th>class</th><th>completed</th><th>SLO goodput</th><th>e2e p95</th><th>svc p95</th><th>SLO miss</th></tr>` +
        (rows.length ? rows.map(r => `<tr><td>${r.name}</td><td>${fmt(r.completed,0)}</td><td>${fmt(r.goodput)}</td><td>${sec(r.p95)}</td><td>${sec(r.svcP95)}</td><td>${pct(r.miss)}</td></tr>`).join("") : `<tr><td colspan="6">No class rolling metrics yet</td></tr>`);
    }
    function renderReplay(replay) {
      const grid = document.getElementById("blockGrid");
      const blocks = replay.blocks || [];
      grid.style.gridTemplateColumns = `repeat(${Math.max(16, Math.ceil(Math.sqrt(Math.max(blocks.length, 1))))}, minmax(8px, 1fr))`;
      grid.innerHTML = blocks.map(b => {
        const base = colors[b.state] || "#64748b";
        const opacity = Math.min(1, .35 + Math.log1p(b.hit_count || 0)*.12 + Math.min(b.share_degree || 0, 8)*.05);
        return `<div class="block" title="block ${b.id} ${b.state} hits=${b.hit_count} share=${b.share_degree}" style="background:${base};opacity:${opacity}"></div>`;
      }).join("");
      document.getElementById("replayMeta").textContent = replay.available
        ? `events ${fmt(replay.counters?.events,0)} | hit ${fmt((replay.prefix_hit_rate || 0)*100)}% | evicted ${fmt(replay.counters?.evicted_blocks,0)} | rebuilt ${fmt(replay.counters?.rebuilt_from_eviction,0)}`
        : (replay.message || "No lifecycle stream");
      document.getElementById("legend").innerHTML = Object.entries(colors).map(([k,v]) => `<span><span class="dot" style="background:${v}"></span>${k}</span>`).join("");
    }
    load().catch(err => { document.body.innerHTML = `<pre>${err.stack || err}</pre>`; });
    if (!snapshotMode) {
      window.kvfabricRefreshTimer = setInterval(() => load().catch(console.error), refreshMs);
    }
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    args: argparse.Namespace

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                body = HTML.replace(
                    "__REFRESH_MS__",
                    str(max(int(self.args.refresh_seconds * 1000), 1000)),
                ).encode("utf-8")
                self.send_bytes(200, "text/html; charset=utf-8", body)
                return
            if parsed.path == "/api/snapshot":
                data = build_snapshot(self.args, parse_qs(parsed.query))
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_bytes(200, "application/json; charset=utf-8", body)
                return
            self.send_bytes(404, "text/plain; charset=utf-8", b"not found")
        except Exception as exc:  # noqa: BLE001
            payload = {"error": type(exc).__name__, "message": str(exc)}
            self.send_bytes(
                500,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )

    def do_HEAD(self) -> None:  # noqa: N802
        if urlparse(self.path).path in {"/", "/index.html", "/api/snapshot"}:
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


def main() -> None:
    args = parse_args()
    Handler.args = args
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"KVFabric static dashboard: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
