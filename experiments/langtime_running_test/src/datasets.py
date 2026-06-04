from __future__ import annotations

import json
import os
import random
import urllib.request
from pathlib import Path
from typing import Any

from src.config import DatasetSourceConfig


class DatasetManager:
    """Download and cache datasets locally. Supports JSON URL and HuggingFace Hub."""

    def __init__(self, cache_dir: str | Path, sources: list[DatasetSourceConfig]):
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sources = sources

    def download_all(self) -> None:
        """Download all configured datasets that aren't already cached."""
        for source in self.sources:
            if source.format == "json":
                self._download_json(source)
            elif source.format in ("hf", "huggingface"):
                self._download_hf(source)

    def _download_json(self, source: DatasetSourceConfig) -> Path:
        target = self.cache_dir / f"{source.name}.json"
        if target.exists():
            return target

        print(f"  正在下载 {source.name} ...")
        req = urllib.request.Request(
            source.url,
            headers={"User-Agent": "KVFabric-bench/0.1"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            target.write_bytes(resp.read())

        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"  已下载 {source.name} → {target} ({size_mb:.1f} MB)")
        return target

    def _download_hf(self, source: DatasetSourceConfig) -> Path:
        """Download from HuggingFace Hub and cache as local JSON.

        Set HF_ENDPOINT=https://hf-mirror.com for faster download in China.
        """
        target = self.cache_dir / f"{source.name}.json"
        if target.exists():
            return target

        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError(
                "需要安装 datasets 库来下载 HuggingFace 数据集。"
                "请执行: pip install datasets"
            )

        split = getattr(source, "split", "train")
        max_samples = getattr(source, "max_samples", 5000)

        endpoint = os.environ.get("HF_ENDPOINT", "")
        if endpoint:
            print(f"  使用 HF 镜像: {endpoint}")

        print(f"  正在从 HuggingFace 下载 {source.name} (split={split}, max={max_samples}) ...")
        ds = load_dataset(source.url, split=split, streaming=True)
        rows = []
        for i, row in enumerate(ds):
            rows.append(row)
            if i + 1 >= max_samples:
                break

        target.write_text(
            json.dumps(rows, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"  已缓存 {source.name} → {target} ({len(rows)} 条, {size_mb:.1f} MB)")
        return target

    def load(self, name: str) -> list[dict[str, Any]]:
        """Load a cached dataset into memory."""
        target = self.cache_dir / f"{name}.json"
        if not target.exists():
            raise FileNotFoundError(
                f"数据集 '{name}' 未下载。请先调用 download_all() 或手动下载到 {target}"
            )
        data = json.loads(target.read_text(encoding="utf-8"))
        source = next((s for s in self.sources if s.name == name), None)

        if source and source.format == "json":
            fields = source.fields
            conv_field = fields.get("conversations", "conversations")
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and conv_field in data:
                return data[conv_field]

        # HF datasets return a list of rows directly
        return data if isinstance(data, list) else []

    def sample_user_messages(
        self,
        name: str,
        count: int,
        strategy: str = "sequential",
        offset: int = 0,
    ) -> list[str]:
        """Extract user messages from a dataset for the cloud model to reference."""
        conversations = self.load(name)

        source = next((s for s in self.sources if s.name == name), None)
        fmt = source.format if source else "json"

        all_user_msgs: list[str] = self._extract_user_messages(
            conversations, source, fmt
        )

        if not all_user_msgs:
            raise ValueError(f"数据集 '{name}' 中没有找到用户消息")

        if strategy == "random":
            selected = random.sample(
                all_user_msgs, min(count, len(all_user_msgs))
            )
        else:
            idx = offset % len(all_user_msgs)
            selected = []
            for i in range(count):
                selected.append(all_user_msgs[(idx + i) % len(all_user_msgs)])

        return selected

    def _extract_user_messages(
        self,
        conversations: list[dict],
        source: DatasetSourceConfig | None,
        fmt: str,
    ) -> list[str]:
        """Extract user/human messages from dataset rows."""
        msgs: list[str] = []

        if fmt == "hf":
            # LMSYS-Chat-1M format: each row has "conversation" list of {role, content}
            for row in conversations:
                if isinstance(row, dict):
                    conv = row.get("conversation", [])
                elif isinstance(row, list):
                    conv = row
                else:
                    conv = []
                for turn in conv:
                    if isinstance(turn, dict):
                        role = str(turn.get("role", "")).lower()
                        content = str(turn.get("content", ""))
                        if role in ("human", "user") and content:
                            msgs.append(content)
            return msgs

        # ShareGPT format
        field_cfg = source.fields if source else {}
        role_from = field_cfg.get("role_from", "from")
        role_value = field_cfg.get("role_value", "value")

        for conv in conversations:
            turns = conv if isinstance(conv, list) else conv.get("turns", [])
            for turn in turns:
                if isinstance(turn, dict):
                    role = str(turn.get(role_from, "")).lower()
                    content = str(turn.get(role_value, ""))
                    if role in ("human", "user") and content:
                        msgs.append(content)
        return msgs
