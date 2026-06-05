from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize KVFabric lifecycle JSONL events."
    )
    parser.add_argument("--input", required=True, help="KVFabric lifecycle JSONL.")
    parser.add_argument("--output", help="Optional metrics JSON output path.")
    return parser.parse_args()


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}") from exc
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts = Counter(event.get("event", "unknown") for event in events)
    prefix_lookups = [e for e in events if e.get("event") == "prefix_lookup"]
    evictions = [e for e in events if e.get("event") == "block_evicted"]
    seals = [e for e in events if e.get("event") == "block_sealed"]
    touches = [e for e in events if e.get("event") == "block_touched"]
    rankings = [
        e for e in events if e.get("event") == "eviction_candidates_ranked"
    ]
    admission_limits = [
        e for e in events if e.get("event") == "cache_admission_limited"
    ]

    prefix_query_tokens = sum(int(e.get("prompt_tokens", 0)) for e in prefix_lookups)
    prefix_hit_tokens = sum(int(e.get("hit_tokens", 0)) for e in prefix_lookups)
    rebuilt_blocks = [e for e in seals if e.get("rebuilt_from_eviction")]

    shared_anchor_evictions = [
        e
        for e in evictions
        if int(e.get("share_degree", 0)) > 1 or int(e.get("hit_count", 0)) > 0
    ]
    tail_evictions = [e for e in evictions if int(e.get("prefix_depth", 0)) <= 1]
    protected_evictions = [
        e
        for e in evictions
        if int(e.get("hit_count", 0)) > 0
        or int(e.get("share_degree", 0)) > 1
        or int(e.get("branch_factor", 0)) > 0
    ]
    hashed_candidate_count = sum(
        int(e.get("candidate_hashed_count", 0)) for e in rankings
    )
    protected_candidate_count = sum(
        int(e.get("candidate_protected_count", 0)) for e in rankings
    )
    selected_hashed_count = sum(
        int(e.get("selected_hashed_count", 0)) for e in rankings
    )
    selected_protected_count = sum(
        int(e.get("selected_protected_count", 0)) for e in rankings
    )
    admission_original_blocks = sum(
        int(e.get("original_full_blocks", 0)) for e in admission_limits
    )
    admission_limited_blocks = sum(
        int(e.get("limited_full_blocks", 0)) for e in admission_limits
    )
    admission_saved_blocks = max(admission_original_blocks - admission_limited_blocks, 0)

    return {
        "events": dict(sorted(event_counts.items())),
        "total_events": len(events),
        "prefix_lookups": len(prefix_lookups),
        "prefix_query_tokens": prefix_query_tokens,
        "prefix_hit_tokens": prefix_hit_tokens,
        "prefix_hit_rate": (
            prefix_hit_tokens / prefix_query_tokens if prefix_query_tokens else 0.0
        ),
        "sealed_blocks": len(seals),
        "touched_blocks": len(touches),
        "evicted_blocks": len(evictions),
        "eviction_ranking_events": len(rankings),
        "cache_admission_limited_events": len(admission_limits),
        "cache_admission_original_blocks": admission_original_blocks,
        "cache_admission_limited_blocks": admission_limited_blocks,
        "cache_admission_saved_blocks": admission_saved_blocks,
        "cache_admission_saved_ratio": (
            admission_saved_blocks / admission_original_blocks
            if admission_original_blocks
            else 0.0
        ),
        "eviction_policies": sorted(
            {
                str(e.get("policy"))
                for e in rankings
                if e.get("policy") is not None
            }
        ),
        "rebuilt_from_eviction_blocks": len(rebuilt_blocks),
        "regretful_eviction_proxy_rate": (
            len(rebuilt_blocks) / len(evictions) if evictions else 0.0
        ),
        "shared_anchor_eviction_ratio": (
            len(shared_anchor_evictions) / len(evictions) if evictions else 0.0
        ),
        "protected_eviction_ratio": (
            len(protected_evictions) / len(evictions) if evictions else 0.0
        ),
        "tail_eviction_ratio": (
            len(tail_evictions) / len(evictions) if evictions else 0.0
        ),
        "avg_evicted_retain_score": (
            sum(float(e.get("retain_score", 0.0)) for e in evictions)
            / len(evictions)
            if evictions
            else 0.0
        ),
        "ranking_hashed_candidate_count": hashed_candidate_count,
        "ranking_protected_candidate_count": protected_candidate_count,
        "ranking_selected_hashed_count": selected_hashed_count,
        "ranking_selected_protected_count": selected_protected_count,
        "ranking_protected_candidate_ratio": (
            protected_candidate_count / hashed_candidate_count
            if hashed_candidate_count
            else 0.0
        ),
        "ranking_selected_protected_ratio": (
            selected_protected_count / selected_hashed_count
            if selected_hashed_count
            else 0.0
        ),
        "avg_selected_retain_score": (
            sum(float(e.get("selected_avg_retain_score", 0.0)) for e in rankings)
            / len(rankings)
            if rankings
            else 0.0
        ),
    }


def main() -> None:
    args = parse_args()
    metrics = summarize(load_events(Path(args.input)))
    payload = json.dumps(metrics, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
