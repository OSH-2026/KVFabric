from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from src.config import CloudUserConfig, VLLMConfig
from src.retry import retry_with_backoff


@dataclass
class ModelResponse:
    """Unified response from any model."""

    content: str
    latency_seconds: float
    model: str
    usage: dict[str, int] | None = None


class CloudModel:
    """Wraps the cloud LLM API that plays the user role."""

    def __init__(self, config: CloudUserConfig):
        api_key = config.resolve_api_key()
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=api_key,
            timeout=60.0,
        )
        self.model_name = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    def invoke(self, messages: list[dict[str, str]]) -> ModelResponse:
        """Send messages to the cloud model and return the reply."""

        def _call() -> ModelResponse:
            started = time.perf_counter()
            result = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            elapsed = time.perf_counter() - started
            content = result.choices[0].message.content or ""
            usage = {}
            if result.usage:
                usage = {
                    "input_tokens": result.usage.prompt_tokens or 0,
                    "output_tokens": result.usage.completion_tokens or 0,
                }
            return ModelResponse(
                content=content,
                latency_seconds=elapsed,
                model=self.model_name,
                usage=usage,
            )

        return retry_with_backoff(
            _call,
            max_tries=3,
            base_delay=2.0,
            description=f"cloud:{self.model_name}",
        )


class VLLMModel:
    """Wraps the local vLLM deployment."""

    def __init__(self, config: VLLMConfig):
        self._client = OpenAI(
            base_url=config.base_url,
            api_key="not-needed",
            timeout=config.timeout_seconds,
        )
        self.model_name = config.model
        self.base_url = config.base_url
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    def invoke(self, messages: list[dict[str, str]]) -> ModelResponse:
        """Send messages to vLLM and return the reply."""

        def _call() -> ModelResponse:
            started = time.perf_counter()
            result = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            elapsed = time.perf_counter() - started
            content = result.choices[0].message.content or ""
            usage = {}
            if result.usage:
                usage = {
                    "input_tokens": result.usage.prompt_tokens or 0,
                    "output_tokens": result.usage.completion_tokens or 0,
                }
            return ModelResponse(
                content=content,
                latency_seconds=elapsed,
                model=self.model_name,
                usage=usage,
            )

        return retry_with_backoff(
            _call,
            max_tries=2,
            base_delay=1.0,
            description=f"vllm:{self.model_name}",
        )
