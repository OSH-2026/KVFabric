from __future__ import annotations

from typing import Any

from src.modes.base import ConversationMode
from src.personas import get_persona, list_personas


class PersonaRotationMode(ConversationMode):
    """Rotates through different user personas, each with a distinct style."""

    def __init__(self, mode_config: dict[str, Any]):
        super().__init__(mode_config)
        names = mode_config.get("personas", list_personas())
        self.personas = [get_persona(n) for n in names]
        self.rounds_per = int(mode_config.get("rounds_per_persona", 10))
        self._current_idx = 0
        self._round_in_persona = 0

    @property
    def current_persona(self):
        return self.personas[self._current_idx % len(self.personas)]

    def get_label(self) -> str:
        return "角色轮换"

    def get_persona_label(self) -> str:
        return self.current_persona.label

    def get_scene_instruction(self) -> str:
        return self.current_persona.system_prompt

    def on_round_start(self, round_num: int) -> None:
        self._round_in_persona += 1
        if self._round_in_persona > self.rounds_per:
            self._round_in_persona = 1
            self._current_idx += 1

    def get_metadata(self) -> dict:
        return {
            "mode_type": "persona_rotation",
            "current_persona": self.current_persona.name,
            "persona_index": self._current_idx,
            "round_in_persona": self._round_in_persona,
        }
