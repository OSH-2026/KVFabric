from __future__ import annotations

from typing import Any

from src.modes.base import ConversationMode

_CONTINUOUS_INSTRUCTION = """你正在和一个 AI 助手进行持续的深度对话，当前话题是: {topic}

请用自然的中文向助手提出下一个问题。规则:
- 围绕当前话题深入追问，逐步探讨更细节的层面
- 每 {questions_per_topic} 轮之后自动切换到下一个相关话题
- 偶尔可以追问对方上一轮的回答（比如 "那具体怎么实现呢？"）
- 每次只问一个问题，不附加任何前缀说明
- 像真实的初学者/技术人员一样提问，不要显得像测试脚本"""


class ContinuousMode(ConversationMode):
    """Deep-dive into a single topic, then switch."""

    def __init__(self, mode_config: dict[str, Any]):
        super().__init__(mode_config)
        self.topic_index = 0
        self.round_in_topic = 0
        self.topics = self._build_topic_list()

    def _build_topic_list(self) -> list[str]:
        initial = self.mode_config.get("initial_topic", "Python 编程")
        extras = self.mode_config.get("extra_topics", [])
        return [initial] + list(extras)

    @property
    def current_topic(self) -> str:
        return self.topics[self.topic_index % len(self.topics)]

    @property
    def questions_per_topic(self) -> int:
        return int(self.mode_config.get("questions_per_topic", 6))

    def get_label(self) -> str:
        return "连续追问"

    def get_persona_label(self) -> str:
        return f"问答者({self.current_topic})"

    def get_scene_instruction(self) -> str:
        return _CONTINUOUS_INSTRUCTION.format(
            topic=self.current_topic,
            questions_per_topic=self.questions_per_topic,
        )

    def on_round_start(self, round_num: int) -> None:
        self.round_in_topic += 1
        if self.round_in_topic > self.questions_per_topic:
            self.round_in_topic = 1
            self.topic_index += 1

    def get_metadata(self) -> dict:
        return {
            "mode_type": "continuous",
            "current_topic": self.current_topic,
            "round_in_topic": self.round_in_topic,
            "topic_index": self.topic_index,
        }
