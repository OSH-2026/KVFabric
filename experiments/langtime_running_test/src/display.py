from __future__ import annotations

import sys
from typing import Any


class Color:
    """ANSI color helpers."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BLUE = "\033[34m"

    @staticmethod
    def supports_color() -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class DisplayManager:
    """Handles terminal output with optional ANSI colors."""

    def __init__(self, show_dialogue: bool = True, color: bool = True):
        self.show_dialogue = show_dialogue
        self._color = color and Color.supports_color()

    # ── helpers ──────────────────────────────────────────────

    def _c(self, ansi: str, text: str) -> str:
        return f"{ansi}{text}{Color.RESET}" if self._color else text

    def _dim(self, text: str) -> str:
        return self._c(Color.DIM, text)

    def _bold(self, text: str) -> str:
        return self._c(Color.BOLD, text)

    # ── status / thinking ────────────────────────────────────

    def thinking(self, round_num: int, role_label: str, model: str) -> None:
        icon = self._c(Color.YELLOW, "⏳")
        header = self._bold(f"[第{round_num}轮]")
        print(f"\n{icon} {header} {role_label} ({self._dim(model)}) 正在思考...", flush=True)

    def think_done(self, elapsed: float, tokens: int = 0) -> None:
        parts = [f"   {self._c(Color.GREEN, '✅')} 耗时 {elapsed:.1f}s"]
        if tokens:
            parts.append(f" | {tokens} tokens")
            if elapsed > 0:
                parts.append(f" | {tokens / elapsed:.1f} tok/s")
        print("".join(parts), flush=True)

    def think_fail(self, error: str) -> None:
        print(f"   {self._c(Color.RED, '❌')} 失败: {error}", flush=True)

    # ── dialogue ─────────────────────────────────────────────

    def user_message(self, round_num: int, label: str, content: str) -> None:
        if not self.show_dialogue:
            return
        print()
        print(self._bold(f"{self._c(Color.CYAN, '👤')} [{label}] 第{round_num}问:"))
        for line in content.splitlines():
            print(f"  {line}")

    def assistant_message(self, content: str) -> None:
        if not self.show_dialogue:
            return
        print()
        print(self._bold(f"{self._c(Color.MAGENTA, '🤖')} 助手:"))
        for line in content.splitlines():
            print(f"  {line}")

    def separator(self) -> None:
        print(self._dim("─" * 65), flush=True)

    # ── header / footer ──────────────────────────────────────

    def header(self, config_name: str, mode: str, total: int,
               vllm_model: str, vllm_url: str, cloud_model: str) -> None:
        print()
        print(self._bold(self._c(Color.BLUE, "═" * 60)))
        print(self._bold(f"  KVFabric 长时间对话压测"))
        print(f"  配置: {config_name}  |  模式: {mode}  |  目标: {total} 轮")
        print(f"  vLLM:  {vllm_model} @ {vllm_url}")
        print(f"  云端:  {cloud_model}")
        print(self._bold(self._c(Color.BLUE, "═" * 60)))
        print(flush=True)

    def footer(self, total_rounds: int, total_time: float) -> None:
        print()
        print(self._bold(self._c(Color.BLUE, "═" * 60)))
        print(self._bold(f"  完成！共 {total_rounds} 轮，耗时 {total_time:.0f}s"))
        print(self._bold(self._c(Color.BLUE, "═" * 60)))
        print(flush=True)

    # ── metrics snapshot ─────────────────────────────────────

    def metrics_snapshot(self, current_round: int, total: int,
                         metrics: dict[str, Any]) -> None:
        print()
        header = self._bold(f"📊 [指标快照 - 最近轮次]  ({current_round}/{total})")
        print(header)

        fmt_line = "  {:<30} {:>15}"
        print(self._dim(fmt_line.format("指标", "值")))

        for label, value in metrics.items():
            if isinstance(value, float):
                display = f"{value:.3f}"
            else:
                display = str(value)
            print(fmt_line.format(label, display))
        self.separator()

    # ── simple status line ───────────────────────────────────

    def status_line(self, round_num: int, total: int, stats: dict[str, Any]) -> None:
        """Single-line status update (overwrites previous)."""
        parts = [
            f"[{round_num}/{total}]",
            f"ttft_avg={stats.get('ttft_avg', 0):.2f}s",
            f"tok/s={stats.get('throughput_avg', 0):.1f}",
        ]
        print("\r" + "  ".join(parts), end="", flush=True)
