#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


PATTERNS = {
    "load_time_ms": re.compile(r"load time =\s+([0-9.]+) ms"),
    "prompt_eval": re.compile(
        r"prompt eval time =\s+([0-9.]+) ms /\s+([0-9]+) tokens .*?,\s+([0-9.]+) tokens per second"
    ),
    "eval": re.compile(
        r"\beval time =\s+([0-9.]+) ms /\s+([0-9]+) runs\s+\(.*?,\s+([0-9.]+) tokens per second"
    ),
    "total_time_ms": re.compile(r"total time =\s+([0-9.]+) ms /\s+([0-9]+) tokens"),
    "max_rss_kb": re.compile(r"Maximum resident set size \(kbytes\):\s+([0-9]+)"),
    "elapsed": re.compile(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s+(.+)"),
    "exit_status": re.compile(r"Exit status:\s+([0-9]+)"),
}


def parse_elapsed_s(value: str) -> float:
    value = value.strip()
    parts = value.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(value)


def parse_log(path: Path, label: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    row = {"label": label, "file": str(path)}

    m = PATTERNS["load_time_ms"].search(text)
    row["load_time_ms"] = float(m.group(1)) if m else ""

    m = PATTERNS["prompt_eval"].search(text)
    if m:
        row["prompt_eval_ms"] = float(m.group(1))
        row["prompt_tokens"] = int(m.group(2))
        row["prompt_tok_s"] = float(m.group(3))
    else:
        row["prompt_eval_ms"] = row["prompt_tokens"] = row["prompt_tok_s"] = ""

    m = PATTERNS["eval"].search(text)
    if m:
        row["eval_ms"] = float(m.group(1))
        row["eval_runs"] = int(m.group(2))
        row["eval_tok_s"] = float(m.group(3))
    else:
        row["eval_ms"] = row["eval_runs"] = row["eval_tok_s"] = ""

    m = PATTERNS["total_time_ms"].search(text)
    if m:
        row["total_time_ms"] = float(m.group(1))
        row["total_tokens"] = int(m.group(2))
    else:
        row["total_time_ms"] = row["total_tokens"] = ""

    m = PATTERNS["max_rss_kb"].search(text)
    row["max_rss_kb"] = int(m.group(1)) if m else ""

    m = PATTERNS["elapsed"].search(text)
    row["elapsed_s"] = parse_elapsed_s(m.group(1)) if m else ""

    m = PATTERNS["exit_status"].search(text)
    row["exit_status"] = int(m.group(1)) if m else ""

    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()

    rows = [parse_log(Path(p), args.label) for p in args.logs]
    fields = [
        "label",
        "file",
        "load_time_ms",
        "prompt_eval_ms",
        "prompt_tokens",
        "prompt_tok_s",
        "eval_ms",
        "eval_runs",
        "eval_tok_s",
        "total_time_ms",
        "total_tokens",
        "max_rss_kb",
        "elapsed_s",
        "exit_status",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
