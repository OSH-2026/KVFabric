#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


PATTERNS = {
    "total_time_s": re.compile(r"Total time run:\s+([0-9.]+)"),
    "bandwidth_mb_s": re.compile(r"Bandwidth \(MB/sec\):\s+([0-9.]+)"),
    "average_iops": re.compile(r"Average IOPS:\s+([0-9.]+)"),
    "average_latency_s": re.compile(r"Average Latency\(s\):\s+([0-9.]+)"),
    "max_latency_s": re.compile(r"Max latency\(s\):\s+([0-9.]+)"),
    "min_latency_s": re.compile(r"Min latency\(s\):\s+([0-9.]+)"),
}


def infer_case(path: Path) -> dict[str, str]:
    stem = path.stem
    parts = stem.split("_")
    operation = parts[1] if len(parts) >= 2 else stem
    threads = ""
    for part in parts:
        if part.startswith("t") and part[1:].isdigit():
            threads = part[1:]
    return {"case": stem, "operation": operation, "threads": threads}


def parse_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    row = infer_case(path)
    row["file"] = str(path)
    for key, pattern in PATTERNS.items():
        match = pattern.search(text)
        row[key] = match.group(1) if match else ""
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    rows = [parse_file(Path(name)) for name in args.files]
    fields = [
        "case",
        "operation",
        "threads",
        "bandwidth_mb_s",
        "average_iops",
        "average_latency_s",
        "max_latency_s",
        "min_latency_s",
        "total_time_s",
        "file",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
