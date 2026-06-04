#!/usr/bin/env python3
"""KVFabric 长时间对话压测 — 云端模型扮演用户与本地 vLLM 对话。

用法:
    python run_dialogue.py --config config.json
    python run_dialogue.py --config config.json --mode persona_rotation --rounds 200
    python run_dialogue.py --config config.json --mode random_topic --rounds 500
"""

from __future__ import annotations

import argparse
import concurrent.futures
import signal
import sys
import time
from pathlib import Path

from src.config import AppConfig, load_config, prepare_run_dir
from src.conversation import DialogueManager, MetricsAccumulator, RoundRecord
from src.datasets import DatasetManager
from src.display import DisplayManager
from src.models import CloudModel, VLLMModel
from src.recorder import Recorder

from src.modes.continuous import ContinuousMode
from src.modes.random_topic import RandomTopicMode
from src.modes.persona_rotation import PersonaRotationMode
from src.modes.dataset_driven import DatasetDrivenMode
from src.modes.pressure_test import PressureTestMode
from src.modes.multi_turn_fork import MultiTurnForkMode
from src.modes.base import ConversationMode
from src.metrics_scraper import MetricsSnapshotCollector
from src.utils import random_topic

MODE_REGISTRY: dict[str, type[ConversationMode]] = {
    "continuous": ContinuousMode,
    "random_topic": RandomTopicMode,
    "persona_rotation": PersonaRotationMode,
    "dataset_driven": DatasetDrivenMode,
    "pressure_test": PressureTestMode,
    "multi_turn_fork": MultiTurnForkMode,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KVFabric 长时间对话压测")
    parser.add_argument("--config", required=True, help="JSON 配置文件路径")
    parser.add_argument("--mode", default=None, help="覆盖配置文件中的对话模式")
    parser.add_argument("--rounds", type=int, default=None, help="覆盖配置文件中的总轮数")
    parser.add_argument("--no-display", action="store_true", help="关闭对话打印")
    parser.add_argument("--skip-dataset-download", action="store_true", help="跳过数据集下载")
    return parser.parse_args()


def build_mode(config: AppConfig, dataset_mgr: DatasetManager | None) -> ConversationMode:
    mode_name = config.conversation.mode
    mode_config = config.get_mode_config()
    mode_cls = MODE_REGISTRY[mode_name]
    if mode_name == "dataset_driven":
        return mode_cls(mode_config, dataset_manager=dataset_mgr)
    return mode_cls(mode_config)


def run_loop(
    config: AppConfig,
    mode: ConversationMode,
    cloud_model: CloudModel,
    vllm_model: VLLMModel,
    dialogue: DialogueManager,
    display: DisplayManager,
    recorder: Recorder,
    metrics_acc: MetricsAccumulator,
    total_rounds: int,
    kv_collector: MetricsSnapshotCollector | None = None,
) -> int:
    """Run the conversation loop. Returns the number of successful rounds."""
    snapshot_interval = config.display.snapshot_interval_rounds
    batch_size = mode.get_batch_size()
    success_count = 0
    global_round = 0

    for batch_num in range(1, total_rounds + 1):
        # Notify pressure_test mode to prepare batch styles
        if hasattr(mode, "on_batch_start"):
            mode.on_batch_start()

        label = mode.get_label()
        persona_label = mode.get_persona_label()

        # ── 1. Cloud model generates questions ────────────────
        display.thinking(batch_num, f"{label} · {persona_label}", cloud_model.model_name)

        try:
            user_context = dialogue.build_user_context(
                scene_instruction=mode.get_scene_instruction(),
                persona_label=persona_label,
            )
            user_response = cloud_model.invoke(user_context)
        except Exception as exc:
            display.think_fail(str(exc))
            continue

        # Parse into individual questions (batch or single)
        if batch_size > 1 and hasattr(mode, "parse_batch_questions"):
            questions = mode.parse_batch_questions(user_response.content)
            if len(questions) < batch_size:
                # Pad with fallback questions
                while len(questions) < batch_size:
                    questions.append(f"请简要介绍一下{random_topic()}")
        else:
            questions = [user_response.content.strip()]

        questions = [q for q in questions if q]
        if not questions:
            display.think_fail("云端模型返回了空消息，跳过本轮")
            continue

        display.think_done(user_response.latency_seconds)

        # ── 2. Send all questions to vLLM ─────────────────────
        if batch_size > 1:
            # Concurrent batch
            results = _send_concurrent(
                questions=questions,
                mode=mode,
                vllm_model=vllm_model,
                dialogue=dialogue,
                display=display,
                batch_num=batch_num,
            )
        else:
            # Sequential single request
            results = [_send_single(
                user_question=questions[0],
                mode=mode,
                vllm_model=vllm_model,
                dialogue=dialogue,
                display=display,
                round_num=batch_num,
                persona_label=persona_label,
            )]

        # ── 3. Record all results ─────────────────────────────
        for i, result in enumerate(results):
            global_round += 1
            mode.on_round_start(global_round)

            if result is None:
                continue

            user_q, vllm_reply, vllm_latency, vllm_tokens = result
            record = RoundRecord(
                round_num=global_round,
                user_label=persona_label,
                user_content=user_q,
                assistant_content=vllm_reply,
                cloud_latency=user_response.latency_seconds / len(questions),
                vllm_latency=vllm_latency,
                vllm_tokens=vllm_tokens,
            )
            metrics_acc.record(record)
            recorder.log_round(record)
            success_count += 1

            mode.on_round_end(global_round, vllm_reply)

        # ── 4. Trim history ────────────────────────────────────
        trimmed = dialogue.trim_history()
        if trimmed > 0:
            print(f"  (上下文已截断 {trimmed} 轮旧对话)")

        # ── 5. Periodic metrics snapshot ───────────────────────
        if global_round > 0 and global_round % snapshot_interval == 0:
            if display.show_dialogue:
                snap = metrics_acc.snapshot(window=snapshot_interval)
                display.metrics_snapshot(global_round, total_rounds * batch_size, snap)
            if kv_collector is not None:
                kv_collector.collect(global_round)

    return success_count


def _send_single(
    user_question: str,
    mode: ConversationMode,
    vllm_model: VLLMModel,
    dialogue: DialogueManager,
    display: DisplayManager,
    round_num: int,
    persona_label: str,
) -> tuple[str, str, float, int] | None:
    """Send one request to vLLM. Returns (question, reply, latency, tokens) or None."""
    dialogue.add_user_message(user_question)
    display.user_message(round_num, persona_label, user_question)
    display.thinking(round_num, "vLLM 助手", vllm_model.model_name)

    try:
        vllm_msgs = mode.get_vllm_messages(dialogue.get_vllm_messages())
        vllm_response = vllm_model.invoke(vllm_msgs)
        vllm_reply = vllm_response.content.strip()
        vllm_tokens = (vllm_response.usage or {}).get("output_tokens", 0)
        display.think_done(vllm_response.latency_seconds, vllm_tokens)
    except Exception as exc:
        dialogue.remove_last_user_message()
        display.think_fail(str(exc))
        return None

    dialogue.add_assistant_message(vllm_reply)
    display.assistant_message(vllm_reply)
    display.separator()
    return (user_question, vllm_reply, vllm_response.latency_seconds, vllm_tokens)


def _send_concurrent(
    questions: list[str],
    mode: ConversationMode,
    vllm_model: VLLMModel,
    dialogue: DialogueManager,
    display: DisplayManager,
    batch_num: int,
) -> list[tuple[str, str, float, int] | None]:
    """Send multiple requests to vLLM concurrently via thread pool.

    Each worker gets an independent snapshot of the dialogue history,
    so concurrent requests don't corrupt each other's context.
    """
    baseline_snapshot = dialogue.snapshot_messages()

    def _worker(idx: int, question: str):
        import copy
        msgs = copy.deepcopy(baseline_snapshot)
        msgs.append({"role": "user", "content": question})

        print(f"\n{'─' * 30}")
        print(f"  📤 并发#{idx + 1}: {question[:80]}{'...' if len(question) > 80 else ''}")

        try:
            vllm_msgs = mode.get_vllm_messages(msgs)
            started = time.time()
            vllm_response = vllm_model.invoke(vllm_msgs)
            elapsed = time.time() - started
            vllm_reply = vllm_response.content.strip()
            vllm_tokens = (vllm_response.usage or {}).get("output_tokens", 0)
            print(f"  📥 并发#{idx + 1}: {elapsed:.1f}s, {vllm_tokens} tokens")
            msgs.append({"role": "assistant", "content": vllm_reply})
            return (question, vllm_reply, elapsed, vllm_tokens)
        except Exception as exc:
            print(f"  ❌ 并发#{idx + 1} 失败: {exc}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(questions)) as pool:
        futures = {pool.submit(_worker, i, q): i for i, q in enumerate(questions)}
        ordered: dict[int, tuple | None] = {}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                ordered[idx] = future.result()
            except Exception as exc:
                print(f"  并发#{idx + 1} 失败: {exc}")
                ordered[idx] = None

    return [ordered.get(i) for i in range(len(questions))]



def main() -> None:
    args = parse_args()

    # Load config
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)

    # CLI overrides
    if args.mode:
        config.conversation.mode = args.mode
    if args.rounds:
        config.conversation.total_rounds = args.rounds

    total_rounds = config.conversation.total_rounds

    # Display
    show_dialogue = not args.no_display and config.display.show_dialogue
    display = DisplayManager(show_dialogue=show_dialogue, color=config.display.color)

    # Models
    cloud_model = CloudModel(config.cloud_user)
    vllm_model = VLLMModel(config.vllm)

    # Datasets (if needed)
    dataset_mgr: DatasetManager | None = None
    if config.conversation.mode == "dataset_driven" and not args.skip_dataset_download:
        dataset_mgr = DatasetManager(
            cache_dir=config.datasets.cache_dir,
            sources=config.datasets.sources,
        )
        print("正在检查数据集...")
        try:
            dataset_mgr.download_all()
        except Exception as e:
            print(f"  ⚠ 数据集下载失败: {e}（将继续运行，cloud model 无参考）")

    # Conversation mode
    mode = build_mode(config, dataset_mgr)

    # Dialogue manager
    dialogue = DialogueManager(
        vllm_system_prompt=config.conversation.vllm_system_prompt,
        max_recent_rounds=config.conversation.share_rounds_history,
        max_context_tokens=config.conversation.max_context_tokens,
    )

    # Prepare output
    run_dir = prepare_run_dir(config)

    # Recorder
    recorder = Recorder(
        run_dir,
        save_interval=config.output.save_interval_rounds,
    )
    recorder.open()
    recorder.write_config(_config_to_dict(config))

    # KV metrics collector (optional)
    kv_collector: MetricsSnapshotCollector | None = None
    if config.output.collect_kv_metrics:
        kv_collector = MetricsSnapshotCollector(
            metrics_url=config.output.metrics_url,
            output_dir=run_dir,
        )
        kv_collector.open()
        print(f"  📊 KV 指标采集: {config.output.metrics_url}")

    # Metrics accumulator
    metrics_acc = MetricsAccumulator()

    # Header
    display.header(
        config_name=config.name,
        mode=mode.get_label(),
        total=total_rounds,
        vllm_model=vllm_model.model_name,
        vllm_url=vllm_model.base_url,
        cloud_model=cloud_model.model_name,
    )

    # Signal handling
    start_time = time.monotonic()
    interrupted = False

    def _on_interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n⏹ 收到中断信号，正在保存当前进度...")
        raise KeyboardInterrupt

    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_interrupt)

    success_count = 0
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
            kv_collector=kv_collector,
        )
    except KeyboardInterrupt:
        interrupted = True
    finally:
        signal.signal(signal.SIGINT, original_handler)
        if kv_collector is not None:
            kv_collector.close()
        elapsed = time.monotonic() - start_time
        display.footer(success_count, elapsed)
        if success_count > 0:
            recorder.write_summary(metrics_acc, success_count, elapsed, mode.get_label())
        else:
            print("⚠ 没有成功完成任何一轮对话，跳过报告生成。")
        recorder.close()


def _config_to_dict(config: AppConfig) -> dict:
    return {
        "name": config.name,
        "description": config.description,
        "vllm": {
            "base_url": config.vllm.base_url,
            "model": config.vllm.model,
            "temperature": config.vllm.temperature,
            "max_tokens": config.vllm.max_tokens,
        },
        "cloud_user": {
            "provider": config.cloud_user.provider,
            "model": config.cloud_user.model,
            "temperature": config.cloud_user.temperature,
        },
        "conversation": {
            "mode": config.conversation.mode,
            "total_rounds": config.conversation.total_rounds,
        },
    }


if __name__ == "__main__":
    main()
