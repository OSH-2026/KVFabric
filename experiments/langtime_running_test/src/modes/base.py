from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ConversationMode(ABC):
    """Abstract base class for conversation modes."""

    def __init__(self, mode_config: dict[str, Any]):
        self.mode_config = mode_config

    # ── required by subclasses ──────────────────────────────────

    @abstractmethod
    def get_label(self) -> str:
        """Short label shown in terminal (e.g. '面试官', 'random_topic')."""
        ...

    @abstractmethod
    def get_persona_label(self) -> str:
        """Label for the current speaker identity."""
        ...

    @abstractmethod
    def get_scene_instruction(self) -> str:
        """System prompt for the cloud model to play its role."""
        ...

    def get_batch_size(self) -> int:
        """Number of concurrent requests per round (1 = sequential)."""
        return 1

    # ── optional hooks (override in subclasses) ──────────────────

    def get_vllm_system_prompt(self, base_prompt: str) -> str:
        """Return the vLLM system prompt for the current round.

        Subclasses can override this to inject shared prefix text,
        creating realistic prefix-cache workload patterns.
        """
        return base_prompt

    def get_vllm_messages(
        self,
        base_messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Return the full message list for vLLM.

        Subclasses can override this to inject or modify messages.
        The default rebuilds the system prompt if get_vllm_system_prompt
        is overridden.
        """
        system_text = self.get_vllm_system_prompt(
            base_messages[0]["content"] if base_messages and base_messages[0]["role"] == "system" else ""
        )
        result = list(base_messages)
        if result and result[0]["role"] == "system":
            result[0] = {"role": "system", "content": system_text}
        elif system_text:
            result.insert(0, {"role": "system", "content": system_text})
        return result

    # ── lifecycle callbacks ─────────────────────────────────────

    def on_round_start(self, round_num: int) -> None:
        """Called at the beginning of each round."""
        pass

    def on_round_end(self, round_num: int, vllm_reply: str | None) -> None:
        """Called at the end of each round. Subclasses can override to adjust state."""
        pass

    def get_metadata(self) -> dict:
        """Return mode state for logging."""
        return {"mode_type": self.__class__.__name__}
