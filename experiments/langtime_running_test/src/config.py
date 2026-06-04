from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VLLMConfig:
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = "Qwen/Qwen3.5-2B"
    temperature: float = 0.0
    max_tokens: int = 256
    timeout_seconds: float = 120.0


@dataclass
class CloudUserConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.8
    max_tokens: int = 128

    def resolve_api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"环境变量 {self.api_key_env} 未设置。"
                f"请 export {self.api_key_env}=<your-api-key>"
            )
        return key


@dataclass
class ConversationConfig:
    mode: str = "continuous"
    total_rounds: int = 200
    share_rounds_history: int = 5
    vllm_system_prompt: str = "你是一个耐心、专业的技术助手，请用中文简洁回答。"
    max_context_tokens: int = 900
    modes: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DatasetSourceConfig:
    name: str = ""
    url: str = ""
    format: str = "json"
    split: str = "train"
    max_samples: int = 5000
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetsConfig:
    cache_dir: str = "./data"
    sources: list[DatasetSourceConfig] = field(default_factory=list)


@dataclass
class OutputConfig:
    runs_dir: str = "./runs"
    save_dialogue: bool = True
    save_metrics: bool = True
    save_interval_rounds: int = 20
    collect_kv_metrics: bool = False
    metrics_url: str = "http://127.0.0.1:8000/metrics"


@dataclass
class DisplayConfig:
    show_dialogue: bool = True
    show_status_bar: bool = True
    show_metrics_snapshot: bool = True
    snapshot_interval_rounds: int = 10
    color: bool = True


@dataclass
class AppConfig:
    name: str = ""
    description: str = ""
    vllm: VLLMConfig = field(default_factory=VLLMConfig)
    cloud_user: CloudUserConfig = field(default_factory=CloudUserConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    datasets: DatasetsConfig = field(default_factory=DatasetsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    def get_mode_config(self) -> dict[str, Any]:
        return self.conversation.modes.get(self.conversation.mode, {})


def load_config(path: str | Path) -> AppConfig:
    """Load and validate config.json."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    vllm = VLLMConfig(**raw.get("vllm", {}))
    cloud = CloudUserConfig(**raw.get("cloud_user", {}))
    conv_raw = raw.get("conversation", {})
    conv = ConversationConfig(
        mode=conv_raw.get("mode", "continuous"),
        total_rounds=conv_raw.get("total_rounds", 200),
        share_rounds_history=conv_raw.get("share_rounds_history", 5),
        vllm_system_prompt=conv_raw.get("vllm_system_prompt", "你是一个耐心、专业的技术助手，请用中文简洁回答。"),
        max_context_tokens=conv_raw.get("max_context_tokens", 900),
        modes=conv_raw.get("modes", {}),
    )

    ds_raw = raw.get("datasets", {})
    sources = [
        DatasetSourceConfig(
            name=s.get("name", ""),
            url=s.get("url", ""),
            format=s.get("format", "json"),
            split=s.get("split", "train"),
            max_samples=s.get("max_samples", 5000),
            fields=s.get("fields", {}),
        )
        for s in ds_raw.get("sources", [])
    ]
    datasets = DatasetsConfig(
        cache_dir=ds_raw.get("cache_dir", "./data"),
        sources=sources,
    )

    output_raw = raw.get("output", {})
    output = OutputConfig(
        runs_dir=output_raw.get("runs_dir", "./runs"),
        save_dialogue=output_raw.get("save_dialogue", True),
        save_metrics=output_raw.get("save_metrics", True),
        save_interval_rounds=output_raw.get("save_interval_rounds", 20),
        collect_kv_metrics=output_raw.get("collect_kv_metrics", False),
        metrics_url=output_raw.get("metrics_url", "http://127.0.0.1:8000/metrics"),
    )
    display = DisplayConfig(**raw.get("display", {}))

    config = AppConfig(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        vllm=vllm,
        cloud_user=cloud,
        conversation=conv,
        datasets=datasets,
        output=output,
        display=display,
    )

    _validate(config)
    return config


def _validate(config: AppConfig) -> None:
    valid_modes = {
        "continuous", "random_topic", "persona_rotation",
        "dataset_driven", "pressure_test", "multi_turn_fork",
    }
    mode = config.conversation.mode
    if mode not in valid_modes:
        raise ValueError(f"未知的对话模式 '{mode}'，可选: {valid_modes}")

    if config.conversation.total_rounds <= 0:
        raise ValueError("total_rounds 必须 > 0")


def prepare_run_dir(config: AppConfig) -> Path:
    """Create a timestamped run directory and copy config into it.

    Supports LANGTIME_RUNS_DIR env var for external override (e.g. run_compare.py).
    """
    import os
    from datetime import datetime

    override = os.getenv("LANGTIME_RUNS_DIR")
    if override:
        run_dir = Path(override).expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = Path(config.output.runs_dir).expanduser().resolve() / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
