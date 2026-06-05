#!/usr/bin/env python3
import argparse
import csv
import json
import statistics as st
import subprocess
import time
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def docker_exec(container: str, command: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"docker exec {container} bash -lc {json.dumps(command)}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def write_one(item: dict[str, Any], args: argparse.Namespace, payload_dir: Path) -> dict[str, Any]:
    object_name = f"ray_ceph_{item['id']}.txt"
    payload = {
        "id": item["id"],
        "category": item.get("category", ""),
        "prompt": item["prompt"],
        "stored_by": "ray",
    }
    payload_path = payload_dir / object_name
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    container_path = f"/lab4/results/ray_ceph/payloads/{object_name}"

    t0 = time.perf_counter()
    proc = docker_exec(args.container, f"rados -p {args.pool} put {object_name} {container_path}", args.timeout)
    put_latency_s = time.perf_counter() - t0
    stat_proc = docker_exec(args.container, f"rados -p {args.pool} stat {object_name}", args.timeout)
    return {
        "id": item["id"],
        "category": item.get("category", ""),
        "object_name": object_name,
        "payload_bytes": payload_path.stat().st_size,
        "put_latency_s": put_latency_s,
        "put_exit": proc.returncode,
        "stat_exit": stat_proc.returncode,
        "success": proc.returncode == 0 and stat_proc.returncode == 0,
        "stderr": (proc.stderr + stat_proc.stderr).strip()[:500],
    }


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(rows: list[dict[str, Any]], path: Path, total_elapsed_s: float, concurrency: int) -> None:
    latencies = [float(row["put_latency_s"]) for row in rows if row["success"]]
    fields = [
        "label",
        "concurrency",
        "objects",
        "success",
        "total_elapsed_s",
        "avg_put_latency_s",
        "p95_put_latency_s",
        "total_payload_bytes",
    ]
    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[min(len(sorted_latencies) - 1, round((len(sorted_latencies) - 1) * 0.95))] if sorted_latencies else 0
    row = {
        "label": "ray_ceph_store",
        "concurrency": concurrency,
        "objects": len(rows),
        "success": sum(1 for row in rows if row["success"]),
        "total_elapsed_s": f"{total_elapsed_s:.3f}",
        "avg_put_latency_s": f"{(st.mean(latencies) if latencies else 0):.3f}",
        "p95_put_latency_s": f"{p95:.3f}",
        "total_payload_bytes": sum(int(row["payload_bytes"]) for row in rows),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--payload-dir", required=True)
    parser.add_argument("--container", default="lab4-ceph-live")
    parser.add_argument("--pool", default="lab4bench")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    import ray

    prompts = read_jsonl(Path(args.prompts))
    if args.limit:
        prompts = prompts[: args.limit]
    payload_dir = Path(args.payload_dir)
    payload_dir.mkdir(parents=True, exist_ok=True)

    ray.init(ignore_reinit_error=True, include_dashboard=False, log_to_driver=False)
    remote_write = ray.remote(write_one)

    t0 = time.perf_counter()
    rows = []
    pending = []
    next_index = 0
    while next_index < len(prompts) or pending:
        while next_index < len(prompts) and len(pending) < args.concurrency:
            pending.append(remote_write.remote(prompts[next_index], args, payload_dir))
            next_index += 1
        done, pending = ray.wait(pending, num_returns=1)
        row = ray.get(done[0])
        print(f"{row['id']} success={row['success']} put_latency={row['put_latency_s']:.3f}s")
        rows.append(row)
    total_elapsed_s = time.perf_counter() - t0
    ray.shutdown()

    write_jsonl(rows, Path(args.out_jsonl))
    write_summary(rows, Path(args.out_summary), total_elapsed_s, args.concurrency)


if __name__ == "__main__":
    main()
