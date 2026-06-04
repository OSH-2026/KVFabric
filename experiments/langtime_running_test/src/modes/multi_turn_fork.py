from __future__ import annotations

from typing import Any

from src.modes.base import ConversationMode

_DEFAULT_SHARED_PREFIX = (
    "你是一个用于 KV Cache 分叉测试的助手。"
    "KV Cache 复用测试公共前缀。该句用于填充共享前缀长度。"
    "请简洁回答，使用中文。"
)

_MULTI_TURN_SHARED_INSTRUCTION = """你正在和一个 AI 助手进行多轮对话。当前处于"共享对话"阶段。

你们正在讨论：{topic}

这是第 {round_in_shared} / {total_shared} 轮。
请提出一个自然的问题，和之前的对话有逻辑关联。
规则：像真人一样推进对话；每次只问一个问题；话题保持在 {topic} 范围内。"""

_MULTI_TURN_FORK_INSTRUCTION = """你正在和一个 AI 助手进行多轮对话。现在对话进入了分叉后的新方向：{branch_label}

请在共享对话历史的基础上，按照 {branch_label} 的方向继续提问。
你的问题应该和共享阶段有一定关联，但朝着不同的方向发展。
规则：每次只问一个问题；语气自然；不需要提"分叉"或"分支"这些词。"""

_FORK_TOPICS = [
    "Python 异步编程的最佳实践",
    "如何设计一个高可用的 API 网关",
    "Kubernetes 集群的监控与告警方案",
    "LLM 推理服务的性能优化",
]

_FORK_BRANCHES = [
    ("性能方向", "请从性能优化的角度追问"),
    ("安全方向", "请从安全性的角度追问"),
    ("成本方向", "请从成本和资源的角度追问"),
    ("实践方向", "请从具体落地实践的角度追问"),
    ("对比方向", "请从对比分析的角度追问"),
]


class MultiTurnForkMode(ConversationMode):
    """Shared prefix -> fork into branches -> private turns.

    Phase 1 (shared): N turns with a long shared system prompt.
    Phase 2 (fork):  Each branch gets its own private_turns continuation.
    The shared prefix text is injected into vLLM to create block reuse,
    then branches diverge so we can observe fork-aware eviction behavior.
    """

    def __init__(self, mode_config: dict[str, Any]):
        super().__init__(mode_config)
        self.shared_turns = int(mode_config.get("shared_turns", 4))
        self.fork_branches = int(mode_config.get("fork_branches", 3))
        self.private_turns = int(mode_config.get("private_turns", 3))

        self._shared_round = 0
        self._fork_round = 0
        self._branch_index = 0
        self._branch_label = _FORK_BRANCHES[0][0]
        self._phase = "shared"  # shared | fork
        self._topic: str = _FORK_TOPICS[0]
        self._total_forks_done = 0

    def get_label(self) -> str:
        return "分叉测试"

    def get_persona_label(self) -> str:
        if self._phase == "shared":
            return "共享对话"
        return f"分叉-{self._branch_label}"

    def get_scene_instruction(self) -> str:
        if self._phase == "shared":
            return _MULTI_TURN_SHARED_INSTRUCTION.format(
                topic=self._topic,
                round_in_shared=self._shared_round + 1,
                total_shared=self.shared_turns,
            )
        return _MULTI_TURN_FORK_INSTRUCTION.format(
            branch_label=self._branch_label,
        )

    def get_vllm_system_prompt(self, base_prompt: str) -> str:
        """During shared phase, inject shared prefix to create block reuse."""
        if self._phase == "shared":
            return self.mode_config.get("shared_system_prompt", _DEFAULT_SHARED_PREFIX)
        return "你是一个 AI 助手。请简洁回答。"

    def on_round_start(self, round_num: int) -> None:
        if self._phase == "shared":
            self._shared_round += 1
            if self._shared_round >= self.shared_turns:
                self._phase = "fork"
                self._fork_round = 0
                self._branch_index = 0
                self._pick_branch()
        elif self._phase == "fork":
            self._fork_round += 1
            if self._fork_round >= self.private_turns:
                self._fork_round = 0
                self._branch_index += 1
                self._total_forks_done += 1
                if self._branch_index >= self.fork_branches:
                    self._branch_index = 0
                self._pick_branch()

    def _pick_branch(self) -> None:
        entry = _FORK_BRANCHES[self._branch_index % len(_FORK_BRANCHES)]
        self._branch_label = entry[0]

    def get_metadata(self) -> dict:
        return {
            "mode_type": "multi_turn_fork",
            "phase": self._phase,
            "shared_round": self._shared_round,
            "fork_round": self._fork_round,
            "branch_label": self._branch_label,
            "branch_index": self._branch_index,
            "total_forks_done": self._total_forks_done,
        }
