from __future__ import annotations

from typing import Any

from src.datasets import DatasetManager
from src.modes.base import ConversationMode

_DATASET_INSTRUCTION = """你正在模拟一个真实用户向 AI 助手提问。请参考下面的示例问题，模仿其风格用中文提出一个全新的问题。

{reference_questions}

规则:
- 可以借用示例中的话题方向，但不要照抄，要提出你自己的问题
- 语气自然，像真人聊天一样
- 每次只问一个问题
- 不附加任何前缀标签"""


class DatasetDrivenMode(ConversationMode):
    """Uses downloaded datasets as style/topic reference for the cloud model.

    When prefix_with_shared_system is enabled, all vLLM requests share
    a long common system prompt, creating realistic prefix-cache workload.
    """

    def __init__(
        self,
        mode_config: dict[str, Any],
        dataset_manager: DatasetManager | None = None,
    ):
        super().__init__(mode_config)
        self.dataset_manager = dataset_manager
        self.dataset_name = mode_config.get("dataset", "sharegpt")
        self.strategy = mode_config.get("sample_strategy", "sequential")
        self.prefix_with_shared_system = mode_config.get("prefix_with_shared_system", False)
        self.shared_system_prompt = mode_config.get("shared_system_prompt", "")

        self._reference_samples: list[str] = []
        self._offset = 0
        self._refs_per_round = 3

    def get_label(self) -> str:
        return "数据集驱动"

    def get_persona_label(self) -> str:
        label = f"数据驱动({self.dataset_name})"
        if self.prefix_with_shared_system:
            label += "+共享前缀"
        return label

    def get_scene_instruction(self) -> str:
        if self.dataset_manager:
            try:
                self._reference_samples = self.dataset_manager.sample_user_messages(
                    self.dataset_name,
                    count=self._refs_per_round,
                    strategy=self.strategy,
                    offset=self._offset,
                )
                self._offset += self._refs_per_round
            except Exception:
                self._reference_samples = []
        refs = "\n".join(f"  - {s[:200]}" for s in self._reference_samples)
        return _DATASET_INSTRUCTION.format(reference_questions=refs or "(无参考)")

    def get_vllm_system_prompt(self, base_prompt: str) -> str:
        """Inject shared system prefix to create prefix-cache workload."""
        if self.prefix_with_shared_system and self.shared_system_prompt:
            return self.shared_system_prompt
        return base_prompt

    def get_metadata(self) -> dict:
        return {
            "mode_type": "dataset_driven",
            "dataset": self.dataset_name,
            "strategy": self.strategy,
            "sample_offset": self._offset,
            "prefix_with_shared": self.prefix_with_shared_system,
        }
