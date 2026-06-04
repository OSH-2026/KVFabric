from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    max_tries: int = 3,
    base_delay: float = 1.0,
    description: str = "request",
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: The function to call.
        max_tries: Maximum number of attempts.
        base_delay: Initial delay in seconds, doubles each retry.
        description: Human-readable label for error messages.

    Returns:
        The return value of `func` on the first successful attempt.

    Raises:
        RuntimeError: If all attempts fail.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_tries + 1):
        try:
            return func()
        except Exception as exc:
            last_exception = exc
            if attempt < max_tries:
                delay = base_delay * (2 ** (attempt - 1))
                print(
                    f"  ⚠ {description} 失败 (attempt {attempt}/{max_tries})，"
                    f"{delay:.1f}s 后重试: {exc}"
                )
                time.sleep(delay)

    raise RuntimeError(
        f"{description} 在 {max_tries} 次尝试后全部失败: {last_exception}"
    )
