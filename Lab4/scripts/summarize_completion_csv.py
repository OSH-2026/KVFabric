#!/usr/bin/env python3
import argparse
import csv
import statistics as st
from pathlib import Path


METRICS = [
    "load_time_ms",
    "prompt_tok_s",
    "eval_tok_s",
    "total_time_ms",
    "max_rss_kb",
    "elapsed_s",
]


def summarize(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    out = []
    label = rows[0]["label"] if rows else path.stem
    for metric in METRICS:
        vals = [float(r[metric]) for r in rows if r.get(metric)]
        if not vals:
            continue
        out.append(
            {
                "label": label,
                "metric": metric,
                "n": len(vals),
                "avg": st.mean(vals),
                "min": min(vals),
                "max": max(vals),
                "stdev": st.stdev(vals) if len(vals) > 1 else 0.0,
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("csv_files", nargs="+")
    args = parser.parse_args()

    all_rows = []
    for name in args.csv_files:
        all_rows.extend(summarize(Path(name)))

    fields = ["label", "metric", "n", "avg", "min", "max", "stdev"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    for row in all_rows:
        print(
            f"{row['label']} {row['metric']}: "
            f"n={row['n']} avg={row['avg']:.2f} min={row['min']:.2f} "
            f"max={row['max']:.2f} stdev={row['stdev']:.2f}"
        )


if __name__ == "__main__":
    main()
