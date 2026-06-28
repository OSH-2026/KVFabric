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
from kvfabric_run_reader import KVFabricRunReader, POLICIES  # noqa: E402


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
    current_policy = query.get("policy", [reader.current_policy()])[0]
    if current_policy not in POLICIES:
        current_policy = reader.current_policy()
    snapshots = reader.policy_snapshots()
    policy_rows = []
    for item in snapshots:
        policy_rows.append(
            {
                "policy": item.policy,
                "status": item.inferred_status,
                "completed": metric(item, "completed", metric(item, "requests", 0)),
                "offered": metric(item, "offered", 0),
                "tok_s": metric(item, "total_tokens_per_second", 0.0),
                "goodput_tok_s": metric(item, "goodput_total_tokens_per_second", 0.0),
                "avg_latency_s": metric(item, "latency_avg_seconds", 0.0),
                "p95_latency_s": metric(item, "latency_p95_seconds", 0.0),
                "prefix_hit_rate": item.lifecycle_metrics.get("prefix_hit_rate"),
                "rebuilt": item.lifecycle_metrics.get("rebuilt_from_eviction_blocks"),
                "admission_saved": item.lifecycle_metrics.get(
                    "cache_admission_saved_blocks"
                ),
                "rolling": item.rolling[-240:],
                "last_update_epoch": item.last_update_mtime,
            }
        )
    selected = next(
        (item for item in snapshots if item.policy == current_policy),
        snapshots[-1],
    )
    return {
        "generated_at": time.time(),
        "run_root": str(run_root.resolve()),
        "run_name": run_root.name,
        "run_state": reader.run_state(),
        "trace_summary": reader.trace_summary(),
        "current_policy": current_policy,
        "policies": policy_rows,
        "prometheus": selected.prometheus,
        "raw_outputs": selected.raw_outputs[-20:],
        "job_log_tail": reader.job_log_tail(max_bytes=18000),
        "replay": compact_blocks(
            run_root,
            current_policy,
            limit_events=max(args.lifecycle_event_limit, 1),
        ),
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
      position: sticky;
      top: 0;
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
        <h3>Rolling Throughput / Latency</h3>
        <canvas id="rollingChart" height="260"></canvas>
      </div>
      <div class="panel">
        <h3>KV Cache Replay</h3>
        <div id="replayMeta" class="sub"></div>
        <div id="blockGrid"></div>
        <div class="legend" id="legend"></div>
      </div>
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
    let currentPolicy = "";
    const colors = {
      FREE: "#1f2937", ACTIVE: "#2563eb", SEALED: "#06b6d4",
      SHARED: "#22c55e", COOLING_WARM: "#eab308",
      COOLING_HOT: "#f97316", EVICTED: "#ef4444", REBUILT: "#a855f7"
    };
    const fmt = (v, d=2) => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined, {maximumFractionDigits:d}) : "n/a";
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
      document.getElementById("runLine").textContent = `${data.run_name} | ${data.run_root}`;
      document.getElementById("cards").innerHTML = [
        card("Policy", data.current_policy, selected.status || ""),
        card("Completed", fmt(selected.completed, 0), `offered ${fmt(selected.offered, 0)}`),
        card("Total tok/s", fmt(selected.tok_s), `goodput ${fmt(selected.goodput_tok_s)}`),
        card("P95 latency", `${fmt(selected.p95_latency_s)}s`, `avg ${fmt(selected.avg_latency_s)}s`),
        card("Prefix hit", selected.prefix_hit_rate == null ? "n/a" : `${fmt(selected.prefix_hit_rate * 100)}%`, `rebuilt ${fmt(selected.rebuilt, 0)}`),
        card("KV usage", `${fmt((data.prometheus.kv_cache_usage_perc || 0) * 100)}%`, `waiting ${fmt(data.prometheus.num_requests_waiting || 0, 0)}`)
      ].join("");
      document.getElementById("policyTabs").innerHTML = data.policies.map(p =>
        `<button class="${p.policy === data.current_policy ? "active" : ""}" onclick="currentPolicy='${p.policy}'; load();">${p.policy}</button>`
      ).join("");
      document.getElementById("policyTable").innerHTML =
        `<tr><th>policy</th><th>status</th><th>completed</th><th>tok/s</th><th>goodput</th><th>avg</th><th>p95</th><th>hit</th><th>rebuilt</th><th>saved</th></tr>` +
        data.policies.map(p => `<tr><td>${p.policy}</td><td class="${stateClass(p.status)}">${p.status}</td><td>${fmt(p.completed,0)}</td><td>${fmt(p.tok_s)}</td><td>${fmt(p.goodput_tok_s)}</td><td>${fmt(p.avg_latency_s)}</td><td>${fmt(p.p95_latency_s)}</td><td>${p.prefix_hit_rate == null ? "n/a" : fmt(p.prefix_hit_rate*100)+"%"}</td><td>${fmt(p.rebuilt,0)}</td><td>${fmt(p.admission_saved,0)}</td></tr>`).join("");
      drawChart(selected.rolling || []);
      renderReplay(data.replay || {});
      document.getElementById("samples").textContent = JSON.stringify(data.raw_outputs || [], null, 2);
      document.getElementById("log").textContent = data.job_log_tail || "";
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
        ["total_tokens_per_second", "#38bdf8", "tok/s"],
        ["goodput_total_tokens_per_second", "#22c55e", "goodput"],
        ["latency_p95_seconds", "#f59e0b", "p95"]
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
    setInterval(() => load().catch(console.error), refreshMs);
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


def main() -> None:
    args = parse_args()
    Handler.args = args
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"KVFabric static dashboard: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
