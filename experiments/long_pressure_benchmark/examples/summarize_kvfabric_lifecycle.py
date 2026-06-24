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
    request_finishes = [e for e in events if e.get("event") == "request_finished"]
    request_schedules = [e for e in events if e.get("event") == "request_scheduled"]
    request_deferrals = [e for e in events if e.get("event") == "request_deferred"]
    request_hints = [e for e in events if e.get("event") == "request_hints_observed"]

    prefix_query_tokens = sum(int(e.get("prompt_tokens", 0)) for e in prefix_lookups)
    prefix_hit_tokens = sum(int(e.get("hit_tokens", 0)) for e in prefix_lookups)
    rebuilt_blocks = [e for e in seals if e.get("rebuilt_from_eviction")]
    family_ids = {
        int(e["family_id"])
        for e in events
        if e.get("family_id") is not None
    }
    family_branch_counts = [
        int(e.get("family_branch_count", 0) or 0)
        for e in [*seals, *touches, *evictions]
    ]
    family_hit_counts = [
        int(e.get("family_hit_count", 0) or 0)
        for e in [*seals, *touches, *evictions]
    ]
    family_regret_counts = [
        int(e.get("family_regret_count", 0) or 0)
        for e in [*seals, *touches, *evictions]
    ]

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
        or int(e.get("family_hit_count", 0) or 0) > 0
        or int(e.get("family_branch_count", 0) or 0) > 0
        or int(e.get("family_regret_count", 0) or 0) > 0
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
    admission_risks = [
        float(e.get("eviction_risk_ratio", 0.0) or 0.0)
        for e in admission_limits
    ]
    deferral_risks = [
        float(e.get("eviction_risk_ratio", 0.0) or 0.0)
        for e in request_deferrals
    ]
    scheduled_tokens = sum(
        int(e.get("scheduled_tokens", 0) or 0) for e in request_schedules
    )
    scheduled_local_cached_tokens = sum(
        int(e.get("local_cached_tokens", 0) or 0) for e in request_schedules
    )
    scheduled_external_cached_tokens = sum(
        int(e.get("external_cached_tokens", 0) or 0) for e in request_schedules
    )
    hint_family_latest: dict[str, dict[str, Any]] = {}
    for event in events:
        family_key = event.get("hint_family_key")
        if not family_key:
            continue
        previous = hint_family_latest.get(str(family_key))
        if previous is None or int(event.get("seq", 0)) >= int(previous.get("seq", 0)):
            hint_family_latest[str(family_key)] = event

    def top_hint_families(sort_key: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = []
        for family_key, event in hint_family_latest.items():
            rows.append(
                {
                    "hint_family_key": family_key,
                    "hint_tenant_id": event.get("hint_tenant_id"),
                    "hint_family_id": event.get("hint_family_id"),
                    "hint_family_request_count": int(
                        event.get("hint_family_request_count", 0) or 0
                    ),
                    "hint_family_prefix_hit_tokens": int(
                        event.get("hint_family_prefix_hit_tokens", 0) or 0
                    ),
                    "hint_family_deferred_count": int(
                        event.get("hint_family_deferred_count", 0) or 0
                    ),
                    "hint_family_admission_limited_count": int(
                        event.get("hint_family_admission_limited_count", 0) or 0
                    ),
                    "hint_family_hit_ratio": float(
                        event.get("hint_family_hit_ratio", 0.0) or 0.0
                    ),
                    "hint_family_last_request_class": event.get(
                        "hint_family_last_request_class"
                    ),
                    "hint_family_last_cache_priority": event.get(
                        "hint_family_last_cache_priority"
                    ),
                    "hint_family_last_expected_reuse": event.get(
                        "hint_family_last_expected_reuse"
                    ),
                }
            )
        rows.sort(key=lambda row: row.get(sort_key, 0), reverse=True)
        return rows[:limit]

    return {
        "events": dict(sorted(event_counts.items())),
        "total_events": len(events),
        "prefix_lookups": len(prefix_lookups),
        "prefix_query_tokens": prefix_query_tokens,
        "prefix_hit_tokens": prefix_hit_tokens,
        "prefix_hit_rate": (
            prefix_hit_tokens / prefix_query_tokens if prefix_query_tokens else 0.0
        ),
        "request_finished_events": len(request_finishes),
        "request_scheduled_events": len(request_schedules),
        "request_deferred_events": len(request_deferrals),
        "request_hints_observed_events": len(request_hints),
        "request_hint_coverage_vs_finished": (
            len(request_hints) / len(request_finishes) if request_finishes else 0.0
        ),
        "request_hint_classes": dict(
            sorted(
                Counter(
                    str(e.get("hint_request_class", "unknown"))
                    for e in request_hints
                ).items()
            )
        ),
        "request_hint_cache_priorities": dict(
            sorted(
                Counter(
                    str(e.get("hint_cache_priority", "unknown"))
                    for e in request_hints
                ).items()
            )
        ),
        "request_hint_expected_reuse": dict(
            sorted(
                Counter(
                    str(e.get("hint_expected_reuse", "unknown"))
                    for e in request_hints
                ).items()
            )
        ),
        "hint_family_count": len(hint_family_latest),
        "top_hint_families_by_requests": top_hint_families(
            "hint_family_request_count"
        ),
        "top_hint_families_by_prefix_hits": top_hint_families(
            "hint_family_prefix_hit_tokens"
        ),
        "top_hint_families_by_deferrals": top_hint_families(
            "hint_family_deferred_count"
        ),
        "top_hint_families_by_admission_limits": top_hint_families(
            "hint_family_admission_limited_count"
        ),
        "request_scheduled_tokens": scheduled_tokens,
        "request_scheduled_local_cached_tokens": scheduled_local_cached_tokens,
        "request_scheduled_external_cached_tokens": scheduled_external_cached_tokens,
        "sealed_blocks": len(seals),
        "touched_blocks": len(touches),
        "evicted_blocks": len(evictions),
        "unique_prefix_families": len(family_ids),
        "max_family_branch_count": max(family_branch_counts, default=0),
        "max_family_hit_count": max(family_hit_counts, default=0),
        "max_family_regret_count": max(family_regret_counts, default=0),
        "family_regret_event_count": sum(1 for value in family_regret_counts if value > 0),
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
        "cache_admission_avg_eviction_risk_ratio": (
            sum(admission_risks) / len(admission_risks)
            if admission_risks
            else 0.0
        ),
        "cache_admission_max_eviction_risk_ratio": (
            max(admission_risks) if admission_risks else 0.0
        ),
        "cache_admission_pressure_states": dict(
            sorted(
                Counter(str(e.get("pressure_state", "UNKNOWN")) for e in admission_limits).items()
            )
        ),
        "cache_admission_risk_pressure_states": dict(
            sorted(
                Counter(str(e.get("risk_pressure_state", "UNKNOWN")) for e in admission_limits).items()
            )
        ),
        "cache_admission_request_classes": dict(
            sorted(
                Counter(str(e.get("request_class", "unknown")) for e in admission_limits).items()
            )
        ),
        "cache_admission_hint_classes": dict(
            sorted(
                Counter(
                    str(e.get("hint_request_class", "unknown"))
                    for e in admission_limits
                ).items()
            )
        ),
        "cache_admission_reasons": dict(
            sorted(
                Counter(
                    str(e.get("admission_reason", "unknown"))
                    for e in admission_limits
                ).items()
            )
        ),
        "scheduler_defer_reasons": dict(
            sorted(
                Counter(
                    str(e.get("defer_reason", "unknown"))
                    for e in request_deferrals
                ).items()
            )
        ),
        "scheduler_defer_hint_classes": dict(
            sorted(
                Counter(
                    str(e.get("hint_request_class", "unknown"))
                    for e in request_deferrals
                ).items()
            )
        ),
        "scheduler_defer_avg_eviction_risk_ratio": (
            sum(deferral_risks) / len(deferral_risks)
            if deferral_risks
            else 0.0
        ),
        "scheduler_defer_max_eviction_risk_ratio": (
            max(deferral_risks) if deferral_risks else 0.0
        ),
        "eviction_policies": sorted(
            {
                str(e.get("policy"))
                for e in [*rankings, *evictions]
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
