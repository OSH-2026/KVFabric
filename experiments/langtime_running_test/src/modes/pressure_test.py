from __future__ import annotations

import random
from typing import Any

from src.modes.base import ConversationMode

_DEFAULT_SHARED_PREFIX = (
    "你是一个用于 KV Cache 压力测试的助手。"
    "KV Cache 复用测试公共前缀。该句用于填充共享前缀长度。"
    "请简洁回答，使用中文。"
)

_PRESSURE_INSTRUCTION = """你正在模拟 {count} 个不同的用户同时向 AI 助手提问。请生成 {count} 个各不相同的问题。

规则：
- 每个问题独立一行，用 "---" 分隔
- 覆盖不同领域（技术、生活、常识、编程、科学等）
- 问题之间尽量有差异，不要重复话题
- {style_hint}
- 直接输出问题，不要加编号、前缀或标签"""

_COLD_TOPICS = [
    "分布式数据库的一致性协议",
    "Rust 语言的所有权系统和生命周期标注",
    "深度学习中的注意力机制及其变体",
    "Linux 内核的进程调度算法",
    "编译原理中的 LLVM IR 优化",
    "微服务架构中的服务发现与负载均衡",
    "密码学中的零知识证明原理",
    "量子计算的基本原理和应用前景",
]


class PressureTestMode(ConversationMode):
    """Concurrent mixed workload: shared-prefix + cold requests.

    Each round generates a batch of concurrent requests. Within the batch,
    shared_ratio fraction uses a long shared system prompt (prefix-cache friendly),
    and the rest use minimal prompts with long cold-start questions.
    """

    def __init__(self, mode_config: dict[str, Any]):
        super().__init__(mode_config)
        self.shared_ratio = float(mode_config.get("shared_prefix_ratio", 0.7))
        self.concurrency = int(mode_config.get("concurrency", 4))
        self._shared_count = 0
        self._cold_count = 0
        # Per-request styles within current batch
        self._batch_styles: list[str] = []
        self._batch_index = 0

    def get_label(self) -> str:
        return f"压力测试(并发x{self.concurrency})"

    def get_batch_size(self) -> int:
        return self.concurrency

    def get_persona_label(self) -> str:
        style = self._batch_styles[self._batch_index] if self._batch_index < len(self._batch_styles) else "?"
        return f"共享用户" if style == "shared" else "冷启动用户"

    def get_scene_instruction(self) -> str:
        shared_n = sum(1 for s in self._batch_styles if s == "shared")
        cold_n = len(self._batch_styles) - shared_n
        return _PRESSURE_INSTRUCTION.format(
            count=len(self._batch_styles),
            style_hint=(
                f"其中 {shared_n} 个问题是简短的（因为共享前缀已经很长），"
                f"另外 {cold_n} 个问题本身就很长很详细（包含足够的上下文）"
            ),
        )

    def get_vllm_system_prompt(self, base_prompt: str) -> str:
        """Per-request prompt: shared rounds get long prefix, cold rounds get minimal."""
        if self._batch_index < len(self._batch_styles):
            style = self._batch_styles[self._batch_index]
            if style == "shared":
                return self.mode_config.get("shared_system_prompt", _DEFAULT_SHARED_PREFIX)
        return "你是一个 AI 助手。请简洁回答。"

    def on_batch_start(self) -> None:
        """Called before generating a batch of questions."""
        self._batch_styles = []
        self._batch_index = 0
        for _ in range(self.concurrency):
            style = "shared" if random.random() < self.shared_ratio else "cold"
            self._batch_styles.append(style)
            if style == "shared":
                self._shared_count += 1
            else:
                self._cold_count += 1

    def on_round_start(self, round_num: int) -> None:
        self._batch_index = min(self._batch_index + 1, len(self._batch_styles) - 1)

    def parse_batch_questions(self, text: str) -> list[str]:
        """Split the cloud model's batch response into individual questions."""
        parts = [p.strip() for p in text.split("---")]
        return [p for p in parts if p]

    def get_metadata(self) -> dict:
        return {
            "mode_type": "pressure_test",
            "shared_prefix_ratio": self.shared_ratio,
            "concurrency": self.concurrency,
            "shared_count": self._shared_count,
            "cold_count": self._cold_count,
        }
