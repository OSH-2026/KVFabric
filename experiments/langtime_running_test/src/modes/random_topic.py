from __future__ import annotations

import random
from typing import Any

from src.modes.base import ConversationMode

_RANDOM_INSTRUCTION = """你正在和一个 AI 助手对话。请用中文随机提出一个问题。

当前随机到的话题是: {topic}

规则:
- 基于当前话题提出一个自然的问题，不要任何前缀标签
- 假装你对这个话题有兴趣，可以追问细节
- 每次只问一个问题
- 问题之间要像真实用户一样自然过渡"""


class RandomTopicMode(ConversationMode):
    """Randomly picks a topic each round."""

    def __init__(self, mode_config: dict[str, Any]):
        super().__init__(mode_config)
        topics = mode_config.get("topic_pool", [])
        if not topics:
            topics = ["Python 编程", "算法与数据结构", "Linux 运维", "机器学习基础"]
        self.topic_pool: list[str] = list(topics)
        self.current_topic = ""
        self._used: list[str] = []

    def get_label(self) -> str:
        return "随机话题"

    def get_persona_label(self) -> str:
        return f"随机话题({self.current_topic})"

    def get_scene_instruction(self) -> str:
        return _RANDOM_INSTRUCTION.format(topic=self.current_topic)

    def on_round_start(self, round_num: int) -> None:
        # Pick a topic, trying not to repeat too soon
        available = [t for t in self.topic_pool if t not in self._used[-3:]]
        if not available:
            available = self.topic_pool
        self.current_topic = random.choice(available)
        self._used.append(self.current_topic)

    def get_metadata(self) -> dict:
        return {
            "mode_type": "random_topic",
            "current_topic": self.current_topic,
            "topic_pool_size": len(self.topic_pool),
        }
