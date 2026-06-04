from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.conversation import MetricsAccumulator, RoundRecord


class Recorder:
    """Writes dialogue and metrics to disk."""

    def __init__(self, run_dir: Path, save_interval: int = 20):
        self.run_dir = run_dir
        self.save_interval = save_interval
        self._dialogue_path = run_dir / "dialogue.jsonl"
        self._metrics_path = run_dir / "metrics.jsonl"
        self._summary_path = run_dir / "summary.json"

        self._dialogue_file = None
        self._metrics_file = None
        self._round_count = 0

    def open(self) -> None:
        self._dialogue_file = self._dialogue_path.open("w", encoding="utf-8")
        self._metrics_file = self._metrics_path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._dialogue_file:
            self._dialogue_file.close()
        if self._metrics_file:
            self._metrics_file.close()

    def log_round(self, record: RoundRecord) -> None:
        self._round_count += 1
        if self._dialogue_file:
            self._dialogue_file.write(
                json.dumps(record.to_json(), ensure_ascii=False) + "\n"
            )

        if self._metrics_file and self._round_count % self.save_interval == 0:
            self._metrics_file.write(
                json.dumps({
                    "round": record.round_num,
                    "cloud_latency": record.cloud_latency,
                    "vllm_latency": record.vllm_latency,
                    "vllm_tokens": record.vllm_tokens,
                    "timestamp": record.timestamp,
                }) + "\n"
            )
            self._dialogue_file.flush()
            self._metrics_file.flush()

    def write_config(self, config_data: dict[str, Any]) -> None:
        (self.run_dir / "config.json").write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_summary(
        self,
        metrics: MetricsAccumulator,
        total_rounds: int,
        elapsed_seconds: float,
        mode: str,
    ) -> None:
        final = metrics.final_summary()
        summary = {
            "total_rounds": total_rounds,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "mode": mode,
            "vllm_latency_avg": round(final.get("vllm_latency_avg", 0), 4),
            "vllm_latency_median": round(final.get("vllm_latency_median", 0), 4),
            "vllm_latency_p95": round(final.get("vllm_latency_p95", 0), 4),
            "vllm_tokens_avg": round(final.get("vllm_tokens_avg", 0), 1),
            "vllm_throughput_tok_s": round(final.get("vllm_throughput_tok_s", 0), 2),
            "cloud_latency_avg": round(final.get("cloud_latency_avg", 0), 4),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        }
        self._summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n📁 运行结果已保存至: {self.run_dir}")
        print(f"   对话日志: {self._dialogue_path}")
        print(f"   汇总指标: {self._summary_path}")
