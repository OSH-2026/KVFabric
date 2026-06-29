#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEXT_UNITS = {
    "global_policy": (
        "Stable assistant policy with tool rules, response schema, safety "
        "constraints, tenant routing hints, audit tags, and long lived "
        "operational context. "
    ),
    "tenant": (
        "Tenant catalog metadata, permission boundaries, integration names, "
        "data retention rules, field aliases, and formatting preferences "
        "remain stable across many requests. "
    ),
    "workflow": (
        "Workflow instructions describe reusable fields, shared business "
        "definitions, escalation rules, prior turn state, and repeated "
        "decision criteria for one task family. "
    ),
    "rag_hot": (
        "Reusable enterprise document paragraph with product policy, support "
        "procedure, customer plan names, table fields, exception notes, and "
        "cross references that may be queried again soon. "
    ),
    "rag_cold": (
        "Unique evidence paragraph with one-off ticket notes, retrieval "
        "snippets, timestamps, numeric fields, customer details, attachments, "
        "and context that should not be reused later. "
    ),
    "code": (
        "Repository context includes module paths, function signatures, "
        "configuration snippets, failing test output, and implementation "
        "constraints for a repeated codebase. "
    ),
    "tool": (
        "Tool observation contains structured JSON fields, search results, "
        "database rows, action ids, timestamps, and status updates from an "
        "agent workflow. "
    ),
    "decode": (
        "Creative brief with audience, outline, examples, constraints, and "
        "style notes for a longer generated answer. "
    ),
    "minor_drift": (
        " Trace label and formatting marker changed for this request without "
        "changing the underlying business meaning. "
    ),
    "schema_drift": (
        " Schema version changed and one optional output field was renamed. "
    ),
    "semantic_shift": (
        " Important semantic shift: this request should not inherit stale "
        "decisions from older family members. "
    ),
}


PROFILE_WEIGHTS = {
    "enterprise_mixed": {
        "tenant_workflow_hot": 0.20,
        "rag_qa_hot_docs": 0.15,
        "rag_qa_cold_docs": 0.25,
        "agent_tool_loop": 0.15,
        "multi_turn_support": 0.15,
        "extraction_classification": 0.05,
        "decode_heavy_report": 0.05,
    },
    "general_gateway": {
        "short_chat_qa": 0.25,
        "single_turn_api_task": 0.20,
        "rag_qa": 0.15,
        "summarization_extract": 0.15,
        "code_assist": 0.10,
        "multi_turn_chat": 0.10,
        "decode_heavy_content": 0.05,
    },
    "conversation_sticky": {
        "deep_multi_turn_chat": 0.45,
        "long_doc_followup_qa": 0.25,
        "agent_tool_loop": 0.15,
        "cold_rag_noise": 0.10,
        "decode_heavy_noise": 0.05,
    },
    "daily_dedicated_reuse": {
        "project_code_followup": 0.28,
        "long_doc_research_followup": 0.24,
        "deep_multi_turn_chat": 0.18,
        "agent_tool_loop": 0.10,
        "tenant_workflow_hot": 0.08,
        "background_cold_lookup": 0.06,
        "decode_heavy_background": 0.04,
        "short_chat_qa": 0.02,
    },
    "sticky_burst": {
        "deep_multi_turn_chat": 0.32,
        "long_doc_followup_qa": 0.28,
        "agent_tool_loop": 0.15,
        "project_code_followup": 0.10,
        "cold_rag_noise": 0.08,
        "decode_heavy_noise": 0.07,
    },
    "low_reuse_low_frequency": {
        "rag_qa_cold_docs": 0.26,
        "decode_heavy_background": 0.22,
        "extraction_classification": 0.18,
        "single_turn_api_task": 0.18,
        "short_chat_qa": 0.16,
    },
}


CLASS_LENGTHS = {
    "short_chat_qa": (350, (32, 256)),
    "single_turn_api_task": (900, (32, 512)),
    "rag_qa": (2300, (64, 768)),
    "summarization_extract": (2400, (64, 512)),
    "code_assist": (2300, (128, 1024)),
    "multi_turn_chat": (1400, (32, 512)),
    "decode_heavy_content": (1200, (512, 2048)),
    "tenant_workflow_hot": (1800, (32, 384)),
    "rag_qa_hot_docs": (2700, (64, 768)),
    "rag_qa_cold_docs": (2900, (64, 768)),
    "agent_tool_loop": (2200, (32, 512)),
    "multi_turn_support": (1700, (32, 512)),
    "extraction_classification": (1800, (16, 256)),
    "decode_heavy_report": (1500, (512, 1536)),
    "deep_multi_turn_chat": (2200, (32, 512)),
    "long_doc_followup_qa": (3000, (64, 768)),
    "cold_rag_noise": (3000, (32, 512)),
    "decode_heavy_noise": (1500, (512, 1536)),
    "project_code_followup": (3200, (64, 768)),
    "long_doc_research_followup": (3600, (64, 768)),
    "background_cold_lookup": (2600, (32, 512)),
    "decode_heavy_background": (1400, (512, 1536)),
}


SESSION_CLASSES = {
    "multi_turn_chat",
    "multi_turn_support",
    "deep_multi_turn_chat",
    "long_doc_followup_qa",
    "long_doc_research_followup",
    "project_code_followup",
    "agent_tool_loop",
}


PROFILE_DEFAULTS = {
    "enterprise_mixed": {
        "tenant_count": 12,
        "client_count": 96,
        "hot_family_count": 48,
        "session_family_count": 64,
        "session_reuse_probability": 0.65,
        "session_interval_min_seconds": 10.0,
        "session_interval_max_seconds": 180.0,
        "burst_probability": 0.04,
        "burst_multiplier_min": 1.8,
        "burst_multiplier_max": 3.2,
        "wave_amplitude": 0.25,
    },
    "general_gateway": {
        "tenant_count": 16,
        "client_count": 128,
        "hot_family_count": 64,
        "session_family_count": 96,
        "session_reuse_probability": 0.50,
        "session_interval_min_seconds": 20.0,
        "session_interval_max_seconds": 240.0,
        "burst_probability": 0.03,
        "burst_multiplier_min": 1.5,
        "burst_multiplier_max": 2.5,
        "wave_amplitude": 0.20,
    },
    "conversation_sticky": {
        "tenant_count": 8,
        "client_count": 48,
        "hot_family_count": 48,
        "session_family_count": 64,
        "session_reuse_probability": 0.70,
        "session_interval_min_seconds": 10.0,
        "session_interval_max_seconds": 180.0,
        "burst_probability": 0.04,
        "burst_multiplier_min": 1.8,
        "burst_multiplier_max": 3.2,
        "wave_amplitude": 0.25,
    },
    "daily_dedicated_reuse": {
        "tenant_count": 3,
        "client_count": 8,
        "hot_family_count": 18,
        "session_family_count": 24,
        "session_reuse_probability": 0.86,
        "session_interval_min_seconds": 20.0,
        "session_interval_max_seconds": 240.0,
        "burst_probability": 0.025,
        "burst_multiplier_min": 1.6,
        "burst_multiplier_max": 3.0,
        "wave_amplitude": 0.12,
    },
    "sticky_burst": {
        "tenant_count": 4,
        "client_count": 12,
        "hot_family_count": 24,
        "session_family_count": 32,
        "session_reuse_probability": 0.78,
        "session_interval_min_seconds": 8.0,
        "session_interval_max_seconds": 90.0,
        "burst_probability": 0.10,
        "burst_multiplier_min": 2.2,
        "burst_multiplier_max": 5.0,
        "wave_amplitude": 0.18,
    },
    "low_reuse_low_frequency": {
        "tenant_count": 12,
        "client_count": 96,
        "hot_family_count": 96,
        "session_family_count": 96,
        "session_reuse_probability": 0.10,
        "session_interval_min_seconds": 60.0,
        "session_interval_max_seconds": 300.0,
        "burst_probability": 0.01,
        "burst_multiplier_min": 1.2,
        "burst_multiplier_max": 2.0,
        "wave_amplitude": 0.08,
    },
}


@dataclass
class ActiveSession:
    session_id: str
    tenant_id: str
    client_id: str
    family_id: str
    request_class: str
    max_turns: int
    next_turn: int
    next_time: float
    system: str
    messages: list[dict[str, str]]
    assistant_seed: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic trace for realistic KVFabric runs."
    )
    parser.add_argument("--config", help="Benchmark JSON config.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile", choices=sorted(PROFILE_WEIGHTS), default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--request-rate", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-model-len", type=int, default=None)
    return parser.parse_args()


def load_settings(args: argparse.Namespace) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        settings.update(config.get("trace", {}))
        settings["config_name"] = config.get("name")
    for key, value in {
        "profile": args.profile,
        "duration_seconds": args.duration_seconds,
        "request_rate": args.request_rate,
        "seed": args.seed,
        "max_model_len": args.max_model_len,
    }.items():
        if value is not None:
            settings[key] = value
    settings.setdefault("profile", "enterprise_mixed")
    settings.setdefault("duration_seconds", 3600)
    settings.setdefault("request_rate", 0.4)
    settings.setdefault("seed", 20260624)
    settings.setdefault("max_model_len", 4096)
    settings.setdefault("load_mode", "stress_90")
    settings.setdefault("hint_regime", "partial_hints")
    return settings


def repeat_to_budget(unit: str, target_chars: int) -> str:
    repeat = max(1, math.ceil(target_chars / max(len(unit), 1)))
    return (unit * repeat)[:target_chars]


def sample_max_tokens(rng: random.Random, request_class: str) -> int:
    low, high = CLASS_LENGTHS[request_class][1]
    # Exponential-ish short outputs with a long tail.
    span = high - low
    value = low + int(min(span, rng.expovariate(1 / max(span / 3, 1))))
    if rng.random() < 0.08:
        value = rng.randint(max(low, high // 2), high)
    return max(low, min(high, value))


def choose_weighted(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values())
    pick = rng.random() * total
    acc = 0.0
    for key, weight in weights.items():
        acc += weight
        if pick <= acc:
            return key
    return next(reversed(weights))


def setting_int(settings: dict[str, Any], key: str, default: int) -> int:
    return max(1, int(settings.get(key, default)))


def setting_float(settings: dict[str, Any], key: str, default: float) -> float:
    return float(settings.get(key, default))


def session_depth(rng: random.Random, profile: str) -> int:
    if profile == "daily_dedicated_reuse":
        buckets = [(4, 0.10), (8, 0.35), (12, 0.35), (20, 0.20)]
    elif profile == "sticky_burst":
        buckets = [(2, 0.10), (4, 0.20), (8, 0.35), (16, 0.25), (24, 0.10)]
    elif profile == "low_reuse_low_frequency":
        buckets = [(1, 0.75), (2, 0.20), (4, 0.05)]
    elif profile == "conversation_sticky":
        buckets = [(1, 0.10), (2, 0.15), (4, 0.30), (8, 0.30), (16, 0.15)]
    elif profile == "enterprise_mixed":
        buckets = [(1, 0.25), (2, 0.25), (4, 0.30), (8, 0.15), (16, 0.05)]
    else:
        buckets = [(1, 0.35), (2, 0.25), (4, 0.25), (8, 0.12), (16, 0.03)]
    cap = choose_weighted(rng, {str(k): v for k, v in buckets})
    upper = int(cap)
    lower = 1 if upper <= 2 else upper // 2 + 1
    return rng.randint(lower, upper)


def drift_text(rng: random.Random) -> tuple[str, str]:
    p = rng.random()
    if p < 0.70:
        return "exact", ""
    if p < 0.85:
        return "minor_format", TEXT_UNITS["minor_drift"]
    if p < 0.95:
        return "versioned_schema", TEXT_UNITS["schema_drift"]
    return "semantic_shift", TEXT_UNITS["semantic_shift"]


def base_system(
    tenant_id: str,
    family_id: str,
    request_class: str,
    target_chars: int,
    rng: random.Random,
) -> str:
    drift_mode, drift = drift_text(rng)
    stem = (
        f"Tenant {tenant_id}; family {family_id}; class {request_class}. "
        + repeat_to_budget(TEXT_UNITS["global_policy"], target_chars // 4)
        + repeat_to_budget(TEXT_UNITS["tenant"], target_chars // 4)
        + repeat_to_budget(TEXT_UNITS["workflow"], target_chars // 3)
        + drift
        + f" Drift mode: {drift_mode}. "
    )
    return stem


def make_single_request(
    rng: random.Random,
    request_no: int,
    request_class: str,
    scheduled_at: float,
    profile: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    tenant_count = setting_int(settings, "tenant_count", 12)
    client_count = setting_int(settings, "client_count", 96)
    hot_family_count = setting_int(settings, "hot_family_count", 48)
    cold_family_count = setting_int(settings, "cold_family_count", 256)
    cold_family_reuse_probability = setting_float(
        settings, "cold_family_reuse_probability", 0.0
    )
    tenant = f"tenant-{rng.randint(1, tenant_count):02d}"
    hot = any(
        token in request_class
        for token in ("hot", "workflow", "code", "project", "followup")
    )
    cold = (
        "cold" in request_class
        or "noise" in request_class
        or "background" in request_class
    )
    transient = "near" in request_class
    family_prefix = "hot" if hot else "cold" if cold else "general"
    if hot:
        family_id = f"{family_prefix}-{rng.randint(1, hot_family_count):02d}"
    elif cold and rng.random() < cold_family_reuse_probability:
        family_id = f"{family_prefix}-{rng.randint(1, cold_family_count):03d}"
    else:
        family_id = f"{family_prefix}-{request_no:06d}"
    # The target is a character budget for repeated context units, not an exact
    # tokenizer budget. The full prompt also includes the shared system stem.
    target_chars = int(CLASS_LENGTHS[request_class][0] * rng.uniform(2.4, 3.0))
    system = base_system(tenant, family_id, request_class, target_chars, rng)
    if "rag" in request_class or "doc" in request_class:
        unit = TEXT_UNITS["rag_cold"] if cold else TEXT_UNITS["rag_hot"]
        system += repeat_to_budget(unit, target_chars)
    elif "code" in request_class:
        system += repeat_to_budget(TEXT_UNITS["code"], target_chars)
    elif "decode" in request_class:
        system += repeat_to_budget(TEXT_UNITS["decode"], target_chars // 2)
    else:
        system += repeat_to_budget(TEXT_UNITS["workflow"], target_chars // 2)

    priority = "low" if cold else "high" if hot else "normal"
    reuse = "none" if cold else "durable" if hot else "unknown"
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Request {request_no} for {request_class}. Answer according "
                "to the provided context and keep the response useful."
            ),
        },
    ]
    return {
        "request_id": f"req-{request_no:06d}",
        "scheduled_at_seconds": round(scheduled_at, 3),
        "tenant_id": tenant,
        "client_id": f"client-{rng.randint(1, client_count):03d}",
        "session_id": None,
        "family_id": family_id,
        "turn_index": None,
        "request_class": request_class,
        "expected_reuse": reuse,
        "cache_priority": priority,
        "phase": "steady",
        "burst": False,
        "max_tokens": sample_max_tokens(rng, request_class),
        "temperature": 0.0,
        "messages": messages,
        "profile": profile,
    }


def new_session(
    rng: random.Random,
    request_no: int,
    request_class: str,
    scheduled_at: float,
    profile: str,
    settings: dict[str, Any],
) -> ActiveSession:
    tenant_count = setting_int(settings, "tenant_count", 12)
    client_count = setting_int(settings, "client_count", 96)
    session_family_count = setting_int(settings, "session_family_count", 64)
    tenant = f"tenant-{rng.randint(1, tenant_count):02d}"
    client = f"client-{rng.randint(1, client_count):03d}"
    session_id = f"sess-{request_no:06d}"
    family_id = f"{request_class}-{rng.randint(1, session_family_count):02d}"
    target_chars = int(CLASS_LENGTHS[request_class][0] * rng.uniform(2.2, 2.8))
    system = base_system(tenant, family_id, request_class, target_chars, rng)
    if "doc" in request_class or "research" in request_class:
        system += repeat_to_budget(TEXT_UNITS["rag_hot"], target_chars)
    elif "code" in request_class or "project" in request_class:
        system += repeat_to_budget(TEXT_UNITS["code"], target_chars)
    elif "agent" in request_class:
        system += repeat_to_budget(TEXT_UNITS["tool"], target_chars)
    else:
        system += repeat_to_budget(TEXT_UNITS["workflow"], target_chars)
    return ActiveSession(
        session_id=session_id,
        tenant_id=tenant,
        client_id=client,
        family_id=family_id,
        request_class=request_class,
        max_turns=session_depth(rng, profile),
        next_turn=1,
        next_time=scheduled_at,
        system=system,
        messages=[{"role": "system", "content": system}],
        assistant_seed=(
            "Assistant remembers the tenant policy, prior request facts, tool "
            "outputs, and the current workflow state."
        ),
    )


def materialize_session_request(
    rng: random.Random,
    request_no: int,
    session: ActiveSession,
    scheduled_at: float,
    profile: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    turn = session.next_turn
    messages = list(session.messages)
    messages.append(
        {
            "role": "user",
            "content": (
                f"Turn {turn} in {session.session_id}. Continue the task, "
                "use previous context, and answer the newest user need."
            ),
        }
    )
    entry = {
        "request_id": f"req-{request_no:06d}",
        "scheduled_at_seconds": round(scheduled_at, 3),
        "tenant_id": session.tenant_id,
        "client_id": session.client_id,
        "session_id": session.session_id,
        "family_id": session.family_id,
        "turn_index": turn,
        "request_class": session.request_class,
        "expected_reuse": "durable",
        "cache_priority": "high",
        "phase": "warmup" if turn == 1 else "revisit",
        "burst": False,
        "max_tokens": sample_max_tokens(rng, session.request_class),
        "temperature": 0.0,
        "messages": messages,
        "profile": profile,
    }
    session.messages.append(messages[-1])
    session.messages.append(
        {
            "role": "assistant",
            "content": (
                f"{session.assistant_seed} Synthetic frozen answer for "
                f"turn {turn}; key state remains stable for prefix replay."
            ),
        }
    )
    session.next_turn += 1
    session.next_time = scheduled_at + rng.uniform(
        setting_float(settings, "session_interval_min_seconds", 10.0),
        setting_float(settings, "session_interval_max_seconds", 180.0),
    )
    return entry


def next_arrival_delta(
    rng: random.Random,
    request_rate: float,
    now: float,
    settings: dict[str, Any],
) -> tuple[float, bool]:
    # Mild diurnal wave plus local burstiness; no external dependencies.
    wave = 1.0 + setting_float(settings, "wave_amplitude", 0.25) * math.sin(
        now / 1800.0
    )
    burst = rng.random() < setting_float(settings, "burst_probability", 0.04)
    if burst:
        wave *= rng.uniform(
            setting_float(settings, "burst_multiplier_min", 1.8),
            setting_float(settings, "burst_multiplier_max", 3.2),
        )
    effective_rate = max(request_rate * wave, 1e-6)
    return rng.expovariate(effective_rate), burst


def write_prompt(prompt_dir: Path, entry: dict[str, Any]) -> str:
    prompt_ref = f"prompts/{entry['request_id']}.json"
    prompt_path = prompt_dir / f"{entry['request_id']}.json"
    payload = {"messages": entry.pop("messages")}
    prompt_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return prompt_ref


def generate_trace(settings: dict[str, Any], output_dir: Path) -> None:
    profile = str(settings["profile"])
    effective_settings = dict(PROFILE_DEFAULTS.get(profile, {}))
    effective_settings.update(settings)
    settings = effective_settings
    rng = random.Random(int(settings["seed"]))
    weights = PROFILE_WEIGHTS[profile]
    duration = float(settings["duration_seconds"])
    request_rate = float(settings["request_rate"])

    prompt_dir = output_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "trace.jsonl"
    entries: list[dict[str, Any]] = []
    active_sessions: list[ActiveSession] = []
    now = 0.0
    request_no = 0

    while now < duration:
        delta, burst = next_arrival_delta(rng, request_rate, now, settings)
        now += delta
        if now > duration:
            break
        request_no += 1

        due_sessions = [s for s in active_sessions if s.next_time <= now]
        if due_sessions and rng.random() < setting_float(
            settings, "session_reuse_probability", 0.65
        ):
            session = min(due_sessions, key=lambda item: item.next_time)
            entry = materialize_session_request(
                rng, request_no, session, now, profile, settings
            )
            if session.next_turn > session.max_turns:
                active_sessions.remove(session)
        else:
            request_class = choose_weighted(rng, weights)
            if request_class in SESSION_CLASSES:
                session = new_session(
                    rng, request_no, request_class, now, profile, settings
                )
                entry = materialize_session_request(
                    rng, request_no, session, now, profile, settings
                )
                if session.next_turn <= session.max_turns:
                    active_sessions.append(session)
            else:
                entry = make_single_request(
                    rng, request_no, request_class, now, profile, settings
                )
        entry["burst"] = bool(burst)

        prompt_ref = write_prompt(prompt_dir, entry)
        entry["prompt_ref"] = prompt_ref
        entries.append(entry)

    with trace_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    digest = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    class_counts = Counter(entry["request_class"] for entry in entries)
    reuse_counts = Counter(entry["expected_reuse"] for entry in entries)
    priority_counts = Counter(entry["cache_priority"] for entry in entries)
    burst_count = sum(1 for entry in entries if entry.get("burst"))
    session_request_count = sum(1 for e in entries if e.get("session_id"))
    session_turns = Counter(
        str(entry["turn_index"])
        for entry in entries
        if entry.get("turn_index") is not None
    )
    summary = {
        "trace_sha256": digest,
        "settings": settings,
        "requests": len(entries),
        "duration_seconds": duration,
        "request_rate": request_rate,
        "actual_request_rate": len(entries) / duration if duration > 0 else 0.0,
        "class_counts": dict(sorted(class_counts.items())),
        "expected_reuse_counts": dict(sorted(reuse_counts.items())),
        "cache_priority_counts": dict(sorted(priority_counts.items())),
        "session_turn_counts": dict(sorted(session_turns.items(), key=lambda x: int(x[0]))),
        "session_requests": session_request_count,
        "session_request_ratio": (
            session_request_count / len(entries) if entries else 0.0
        ),
        "burst_requests": burst_count,
        "burst_request_ratio": burst_count / len(entries) if entries else 0.0,
        "unique_sessions": len({e["session_id"] for e in entries if e.get("session_id")}),
        "unique_families": len({e["family_id"] for e in entries if e.get("family_id")}),
        "unique_tenants": len({e["tenant_id"] for e in entries if e.get("tenant_id")}),
        "unique_clients": len({e["client_id"] for e in entries if e.get("client_id")}),
    }
    (output_dir / "trace_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"# Trace Summary: {profile}",
        "",
        f"- Trace SHA256: `{digest}`",
        f"- Requests: {len(entries)}",
        f"- Duration seconds: {duration:.1f}",
        f"- Target request rate: {request_rate:.4f}",
        f"- Actual request rate: {summary['actual_request_rate']:.4f}",
        f"- Hint regime: {settings.get('hint_regime')}",
        f"- Load mode: {settings.get('load_mode')}",
        f"- Session request ratio: {summary['session_request_ratio']:.4f}",
        f"- Burst request ratio: {summary['burst_request_ratio']:.4f}",
        f"- Unique tenants: {summary['unique_tenants']}",
        f"- Unique clients: {summary['unique_clients']}",
        f"- Unique families: {summary['unique_families']}",
        "",
        "## Classes",
        "",
    ]
    for key, value in sorted(class_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Expected Reuse", ""])
    for key, value in sorted(reuse_counts.items()):
        lines.append(f"- {key}: {value}")
    (output_dir / "trace_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    settings = load_settings(args)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_trace(settings, output_dir)
    print(output_dir / "trace_summary.json")


if __name__ == "__main__":
    main()
