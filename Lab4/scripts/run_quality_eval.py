#!/usr/bin/env python3
import argparse
import csv
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


PERF_PATTERNS = {
    "load_time_ms": re.compile(r"load time =\s+([0-9.]+) ms"),
    "prompt_tok_s": re.compile(r"prompt eval time =\s+[0-9.]+ ms /\s+[0-9]+ tokens .*?,\s+([0-9.]+) tokens per second"),
    "eval_tok_s": re.compile(r"\beval time =\s+[0-9.]+ ms /\s+[0-9]+ runs\s+\(.*?,\s+([0-9.]+) tokens per second"),
    "total_time_ms": re.compile(r"total time =\s+([0-9.]+) ms /"),
}


LOG_PREFIXES = (
    "build:",
    "llama_",
    "ggml_",
    "print_info:",
    "load_",
    "common_",
    "sampler",
    "system_info",
    "main:",
    "warning:",
    "error:",
    "Command ",
    "User time ",
    "System time ",
    "Percent of CPU ",
    "Elapsed ",
    "Maximum resident ",
    "Exit status",
)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def extract_metrics(text: str) -> dict:
    out = {}
    for name, pattern in PERF_PATTERNS.items():
        match = pattern.search(text)
        out[name] = float(match.group(1)) if match else None
    return out


def extract_generated_text(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(LOG_PREFIXES):
            continue
        if " = " in stripped and (" ms" in stripped or "tokens" in stripped):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "category",
        "exit_code",
        "wall_time_s",
        "generated_chars",
        "load_time_ms",
        "prompt_tok_s",
        "eval_tok_s",
        "total_time_ms",
        "log_file",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("metrics", {})
            writer.writerow(
                {
                    "id": row["id"],
                    "category": row.get("category", ""),
                    "exit_code": row["exit_code"],
                    "wall_time_s": f"{row['wall_time_s']:.3f}",
                    "generated_chars": len(row.get("generated_text", "")),
                    "load_time_ms": metrics.get("load_time_ms"),
                    "prompt_tok_s": metrics.get("prompt_tok_s"),
                    "eval_tok_s": metrics.get("eval_tok_s"),
                    "total_time_ms": metrics.get("total_time_ms"),
                    "log_file": row["log_file"],
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--label", default="quality")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--temp", type=float, default=0.2)
    parser.add_argument("--default-max-tokens", type=int, default=192)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("extra_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    extra_args = args.extra_args
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    prompts = read_jsonl(Path(args.prompts))
    work_dir = Path(args.work_dir)
    prompt_dir = work_dir / "prompt_files"
    log_dir = work_dir / "logs"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in prompts:
        prompt_id = item["id"]
        prompt_path = prompt_dir / f"{prompt_id}.txt"
        prompt_path.write_text(item["prompt"], encoding="utf-8")
        log_path = log_dir / f"{prompt_id}.log"
        max_tokens = int(item.get("max_tokens") or args.default_max_tokens)
        cmd = [
            args.bin,
            "-m",
            args.model,
            "-f",
            str(prompt_path),
            "-n",
            str(max_tokens),
            "-no-cnv",
            "--threads",
            str(args.threads),
            "--ctx-size",
            str(args.ctx_size),
            "--temp",
            str(args.temp),
            "--no-display-prompt",
            *extra_args,
        ]
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            output = proc.stdout
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            exit_code = 124
        wall_time_s = time.perf_counter() - t0
        log_path.write_text(output, encoding="utf-8")
        rows.append(
            {
                "label": args.label,
                "id": prompt_id,
                "category": item.get("category", ""),
                "prompt": item["prompt"],
                "max_tokens": max_tokens,
                "started_at": started_at,
                "wall_time_s": wall_time_s,
                "exit_code": exit_code,
                "metrics": extract_metrics(output),
                "generated_text": extract_generated_text(output),
                "log_file": str(log_path),
            }
        )
        print(f"{prompt_id}: exit={exit_code} wall={wall_time_s:.2f}s chars={len(rows[-1]['generated_text'])}")

    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_csv(rows, Path(args.out_csv))


if __name__ == "__main__":
    main()
