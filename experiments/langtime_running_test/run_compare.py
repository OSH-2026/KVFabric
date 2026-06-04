#!/usr/bin/env python3
"""KVFabric 对话压测 A/B 对比 — 同一负载下对比不同 KVFabric 策略。

用法:
    python run_compare.py --config config.json --mode persona_rotation --rounds 100
    python run_compare.py --config config.json --mode multi_turn_fork --rounds 100 --variants vanilla,observe,shared_aware

每种 variant 会在不同的环境变量下运行，结果保存到 runs/compare/<timestamp>/ 子目录，
并生成 compare_summary.json 对比报告。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import AppConfig, load_config, prepare_run_dir
from src.conversation import DialogueManager, MetricsAccumulator
from src.datasets import DatasetManager
from src.display import DisplayManager
from src.models import CloudModel, VLLMModel
from src.recorder import Recorder
from run_dialogue import build_mode, run_loop


VARIANTS = {
    "vanilla": {
        "KVFABRIC_LIFECYCLE": "0",
        "label": "vanilla vLLM",
    },
    "observe": {
        "KVFABRIC_LIFECYCLE": "1",
        "KVFABRIC_LIFECYCLE_POLICY": "observe",
        "label": "KVFabric observe",
    },
    "shared_aware": {
        "KVFABRIC_LIFECYCLE": "1",
        "KVFABRIC_LIFECYCLE_POLICY": "shared_aware",
        "label": "KVFabric shared_aware",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KVFabric 对话压测 A/B 对比")
    parser.add_argument("--config", required=True, help="JSON 配置文件路径")
    parser.add_argument("--mode", default=None, help="覆盖对话模式")
    parser.add_argument("--rounds", type=int, default=None, help="每轮对比的总轮数")
    parser.add_argument(
        "--variants",
        default="vanilla,observe",
        help="逗号分隔的策略列表 (默认: vanilla,observe)",
    )
    parser.add_argument("--no-display", action="store_true", help="关闭对话打印")
    return parser.parse_args()


def apply_env(variant_env: dict[str, str]) -> None:
    """Apply variant-specific environment variables."""
    for key, value in variant_env.items():
        os.environ[key] = value


def run_one_variant(
    variant_name: str,
    variant_info: dict,
    config: AppConfig,
    total_rounds: int,
    base_run_dir: Path,
    no_display: bool,
) -> dict:
    """Run the dialogue benchmark for one variant and return summary."""
    # Apply environment variables for this variant
    env_vars = {k: v for k, v in variant_info.items() if k not in ("label",)}
    apply_env(env_vars)

    # Override run directory
    os.environ["LANGTIME_RUNS_DIR"] = str(base_run_dir / variant_name)

    display = DisplayManager(show_dialogue=not no_display, color=True)

    # Models (shared across variants)
    cloud_model = CloudModel(config.cloud_user)
    vllm_model = VLLMModel(config.vllm)

    # Datasets
    dataset_mgr: DatasetManager | None = None
    if config.conversation.mode == "dataset_driven":
        dataset_mgr = DatasetManager(
            cache_dir=config.datasets.cache_dir,
            sources=config.datasets.sources,
        )
        try:
            dataset_mgr.download_all()
        except Exception:
            pass

    # Mode
    mode = build_mode(config, dataset_mgr)

    # Dialogue (fresh per variant)
    dialogue = DialogueManager(
        vllm_system_prompt=config.conversation.vllm_system_prompt,
        max_recent_rounds=config.conversation.share_rounds_history,
    )

    # Output
    run_dir = Path(os.environ["LANGTIME_RUNS_DIR"])
    run_dir.mkdir(parents=True, exist_ok=True)

    recorder = Recorder(run_dir, save_interval=config.output.save_interval_rounds)
    recorder.open()
    recorder.write_config({
        "variant": variant_name,
        "label": variant_info.get("label", variant_name),
        "env": env_vars,
    })

    metrics_acc = MetricsAccumulator()

    description = variant_info.get("label", variant_name)
    print(f"\n{'─' * 60}")
    print(f"  变体: {variant_name} ({description})")
    for k, v in env_vars.items():
        print(f"    {k}={v}")
    print(f"{'─' * 60}\n")

    started = time.monotonic()
    try:
        success_count = run_loop(
            config=config,
            mode=mode,
            cloud_model=cloud_model,
            vllm_model=vllm_model,
            dialogue=dialogue,
            display=display,
            recorder=recorder,
            metrics_acc=metrics_acc,
            total_rounds=total_rounds,
        )
    except KeyboardInterrupt:
        success_count = metrics_acc.total_rounds
    elapsed = time.monotonic() - started

    summary = metrics_acc.final_summary() if success_count > 0 else {}
    recorder.write_summary(metrics_acc, success_count, elapsed, mode.get_label())
    recorder.close()

    return {
        "variant": variant_name,
        "label": variant_info.get("label", variant_name),
        "success_rounds": success_count,
        "elapsed_seconds": round(elapsed, 1),
        "vllm_latency_avg": round(summary.get("vllm_latency_avg", 0), 4),
        "vllm_latency_p95": round(summary.get("vllm_latency_p95", 0), 4),
        "vllm_throughput_tok_s": round(summary.get("vllm_throughput_tok_s", 0), 2),
    }


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    if args.mode:
        config.conversation.mode = args.mode
    total_rounds = args.rounds or config.conversation.total_rounds
    no_display = args.no_display

    variants_to_run = [v.strip() for v in args.variants.split(",")]
    # Validate
    for v in variants_to_run:
        if v not in VARIANTS:
            print(f"错误: 未知 variant '{v}'，可选: {list(VARIANTS)}", file=sys.stderr)
            sys.exit(1)

    # Prepare compare run directory
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    compare_dir = Path("runs/compare").expanduser().resolve() / timestamp
    compare_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for variant_name in variants_to_run:
        variant_info = VARIANTS[variant_name]
        result = run_one_variant(
            variant_name=variant_name,
            variant_info=variant_info,
            config=config,
            total_rounds=total_rounds,
            base_run_dir=compare_dir,
            no_display=no_display,
        )
        results[variant_name] = result

    # Write comparison report
    compare = {
        "timestamp": timestamp,
        "config_mode": config.conversation.mode,
        "total_rounds_per_variant": total_rounds,
        "variants": variants_to_run,
        "results": results,
    }
    (compare_dir / "compare_summary.json").write_text(
        json.dumps(compare, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Print comparison table
    print(f"\n{'=' * 70}")
    print(f"  A/B 对比结果  ({config.conversation.mode}, {total_rounds}轮/变体)")
    print(f"{'=' * 70}")
    print(f"{'变体':<20} {'成功轮':>6} {'耗时(s)':>8} {'avg延迟(s)':>10} {'p95(s)':>8} {'吞吐':>8}")
    print("-" * 70)
    for name in variants_to_run:
        r = results.get(name, {})
        print(
            f"{r.get('label', name):<20} "
            f"{r.get('success_rounds', 0):>6} "
            f"{r.get('elapsed_seconds', 0):>8.0f} "
            f"{r.get('vllm_latency_avg', 0):>10.3f} "
            f"{r.get('vllm_latency_p95', 0):>8.3f} "
            f"{r.get('vllm_throughput_tok_s', 0):>8.1f}"
        )

    print(f"\n📁 对比结果已保存至: {compare_dir}")
    print(f"   各变体详情: {compare_dir}/<variant_name>/")


if __name__ == "__main__":
    main()
