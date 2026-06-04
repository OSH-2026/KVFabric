from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RoundRecord:
    """One round of dialogue with metrics."""

    round_num: int
    user_label: str
    user_content: str
    assistant_content: str

    cloud_latency: float
    vllm_latency: float
    vllm_tokens: int

    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        return {
            "round": self.round_num,
            "user_label": self.user_label,
            "user_content": self.user_content,
            "assistant_content": self.assistant_content,
            "cloud_latency_seconds": round(self.cloud_latency, 3),
            "vllm_latency_seconds": round(self.vllm_latency, 3),
            "vllm_tokens": self.vllm_tokens,
            "timestamp": self.timestamp,
        }


@dataclass
class MetricsAccumulator:
    """Accumulates latency / throughput across rounds."""

    total_rounds: int = 0
    cloud_latencies: list[float] = field(default_factory=list)
    vllm_latencies: list[float] = field(default_factory=list)
    vllm_tokens: list[int] = field(default_factory=list)

    def record(self, record: RoundRecord) -> None:
        self.total_rounds += 1
        self.cloud_latencies.append(record.cloud_latency)
        self.vllm_latencies.append(record.vllm_latency)
        self.vllm_tokens.append(record.vllm_tokens)

    def snapshot(self, window: int = 10) -> dict:
        """Compute summary over the most recent `window` rounds."""
        if not self.vllm_latencies:
            return {}

        recent_v = self.vllm_latencies[-window:]
        recent_c = self.cloud_latencies[-window:]
        recent_t = self.vllm_tokens[-window:]

        total_vllm_time = sum(recent_v)
        total_tokens = sum(recent_t)

        return {
            "vllm_latency_avg": _mean(recent_v),
            "vllm_latency_median": _median(recent_v),
            "vllm_latency_p95": _percentile(recent_v, 0.95),
            "vllm_tokens_avg": _mean(recent_t),
            "vllm_throughput_tok_s": total_tokens / total_vllm_time
            if total_vllm_time > 0 else 0.0,
            "cloud_latency_avg": _mean(recent_c),
            "samples": len(recent_v),
        }

    def final_summary(self) -> dict:
        """Compute summary over all rounds."""
        return self.snapshot(window=len(self.vllm_latencies) or 1)


class DialogueManager:
    """Manages conversation history for both cloud-user and vLLM sides."""

    def __init__(self, vllm_system_prompt: str, max_recent_rounds: int = 5,
                 max_context_tokens: int = 900):
        self.vllm_system_prompt = vllm_system_prompt
        self.max_recent_rounds = max_recent_rounds
        self.max_context_tokens = max_context_tokens

        # Full history as seen by vLLM
        self.vllm_history: list[dict[str, str]] = []
        if vllm_system_prompt:
            self.vllm_history.append({"role": "system", "content": vllm_system_prompt})

        # History seen by the cloud model (the last few rounds)
        self.cloud_history: deque[dict[str, str]] = deque(maxlen=max_recent_rounds * 2)

    @property
    def round_count(self) -> int:
        user_msgs = [m for m in self.vllm_history if m["role"] == "user"]
        return len(user_msgs)

    def add_user_message(self, content: str) -> None:
        self.vllm_history.append({"role": "user", "content": content})

    def remove_last_user_message(self) -> None:
        """Remove the most recent user message (used when vLLM call fails)."""
        for i in range(len(self.vllm_history) - 1, -1, -1):
            if self.vllm_history[i]["role"] == "user":
                self.vllm_history.pop(i)
                return

    def trim_history(self, max_tokens: int | None = None) -> int:
        """Remove oldest user/assistant pairs until total tokens <= max_tokens.

        System prompt is always preserved. Returns the number of pairs removed.
        """
        limit = max_tokens or self.max_context_tokens
        removed = 0

        while True:
            total = self._estimate_total_tokens()
            if total <= limit:
                break

            # Find the first user message after the system prompt
            removed_any = False
            for i, m in enumerate(self.vllm_history):
                if m["role"] in ("user", "assistant"):
                    # Remove this message and its paired response
                    if m["role"] == "user" and i + 1 < len(self.vllm_history):
                        if self.vllm_history[i + 1]["role"] == "assistant":
                            del self.vllm_history[i:i + 2]
                        else:
                            del self.vllm_history[i]
                    else:
                        del self.vllm_history[i]
                    removed += 1
                    removed_any = True
                    break

            if not removed_any:
                break  # can't trim further (only system prompt left)

        return removed

    def _estimate_total_tokens(self) -> int:
        """Rough token estimate: Chinese chars = 1 tok, English words = 1 tok."""
        import re
        total = 0
        for m in self.vllm_history:
            text = m.get("content", "")
            chinese = len(re.findall(r"[一-鿿]", text))
            english = len(re.findall(r"[a-zA-Z0-9]+", text))
            total += chinese + english + len(text) // 4  # fallback for other chars
        return total

    def add_assistant_message(self, content: str) -> None:
        self.vllm_history.append({"role": "assistant", "content": content})

    def get_vllm_messages(self) -> list[dict[str, str]]:
        """Return full vLLM message history (system + all turns)."""
        return list(self.vllm_history)

    def snapshot_messages(self) -> list[dict[str, str]]:
        """Return a deep copy of vLLM messages for concurrent workers."""
        return [dict(m) for m in self.vllm_history]

    def last_assistant_reply(self) -> str | None:
        for m in reversed(self.vllm_history):
            if m["role"] == "assistant":
                return m["content"]
        return None

    def build_user_context(
        self,
        scene_instruction: str,
        persona_label: str,
    ) -> list[dict[str, str]]:
        """Build the cloud model's conversation context (for generating next question).

        Includes: the scene/persona system prompt, the last N rounds of dialogue,
        and a final instruction to continue.
        """
        messages: list[dict[str, str]] = []
        messages.append({"role": "system", "content": scene_instruction})

        recent = self._recent_dialogue_as_text()
        if recent:
            messages.append({
                "role": "system",
                "content": f"以下是近几轮对话历史，请基于此继续：\n{recent}",
            })

        messages.append({
            "role": "user",
            "content": "请提出下一个问题或回应。只输出问题本身，不要加前缀或标签。",
        })
        return messages


    def _recent_dialogue_as_text(self) -> str:
        """Format the last N rounds as plain text."""
        user_msgs = [m for m in self.vllm_history if m["role"] in ("user", "assistant")]
        recent = user_msgs[-(self.max_recent_rounds * 2):]
        lines = []
        for m in recent:
            if m["role"] == "user":
                lines.append(f"用户: {m['content']}")
            else:
                lines.append(f"助手: {m['content']}")
        return "\n".join(lines)


# ── internal stats utils ──────────────────────────────────────

def _mean(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float | int]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _percentile(values: list[float | int], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, round((len(s) - 1) * pct))
    return float(s[idx])
