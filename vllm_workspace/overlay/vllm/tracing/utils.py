# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from collections.abc import Mapping

from vllm.logger import init_logger
from vllm.utils.func_utils import run_once

logger = init_logger(__name__)

# Standard W3C headers used for context propagation
TRACE_HEADERS = ["traceparent", "tracestate"]

# KVFabric request hints are not OpenTelemetry context, but the OpenAI serving
# layer already has a trace_headers path that reaches Request without changing
# public request schemas. These headers are extracted separately so normal W3C
# tracing behavior stays unchanged.
KVFABRIC_HINT_HEADERS = [
    "x-kvfabric-request-class",
    "x-kvfabric-class",
    "x-kvfabric-trace-request-id",
    "x-kvfabric-trace-id",
    "x-kvfabric-tenant-id",
    "x-kvfabric-tenant",
    "x-kvfabric-family-id",
    "x-kvfabric-family",
    "x-kvfabric-cache-priority",
    "x-kvfabric-priority",
    "x-kvfabric-expected-reuse",
    "x-kvfabric-reuse",
    "x-kvfabric-phase",
    "x-kvfabric-burst",
]


def _header_get(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return str(value)
    target = name.lower()
    for key, candidate in headers.items():
        if str(key).lower() == target:
            return str(candidate)
    return None


class SpanAttributes:
    """
    Standard attributes for spans.

    These are largely based on OpenTelemetry Semantic Conventions but are defined
    here as constants so they can be used by any backend or logger.
    """

    # Attribute names copied from OTel semantic conventions to avoid version conflicts
    GEN_AI_USAGE_COMPLETION_TOKENS = "gen_ai.usage.completion_tokens"
    GEN_AI_USAGE_PROMPT_TOKENS = "gen_ai.usage.prompt_tokens"
    GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p"
    GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"

    # Custom attributes added until they are standardized
    GEN_AI_REQUEST_ID = "gen_ai.request.id"
    GEN_AI_REQUEST_N = "gen_ai.request.n"
    GEN_AI_USAGE_NUM_SEQUENCES = "gen_ai.usage.num_sequences"
    GEN_AI_LATENCY_TIME_IN_QUEUE = "gen_ai.latency.time_in_queue"
    GEN_AI_LATENCY_TIME_TO_FIRST_TOKEN = "gen_ai.latency.time_to_first_token"
    GEN_AI_LATENCY_E2E = "gen_ai.latency.e2e"
    GEN_AI_LATENCY_TIME_IN_SCHEDULER = "gen_ai.latency.time_in_scheduler"

    # Latency breakdowns
    GEN_AI_LATENCY_TIME_IN_MODEL_FORWARD = "gen_ai.latency.time_in_model_forward"
    GEN_AI_LATENCY_TIME_IN_MODEL_EXECUTE = "gen_ai.latency.time_in_model_execute"
    GEN_AI_LATENCY_TIME_IN_MODEL_PREFILL = "gen_ai.latency.time_in_model_prefill"
    GEN_AI_LATENCY_TIME_IN_MODEL_DECODE = "gen_ai.latency.time_in_model_decode"
    GEN_AI_LATENCY_TIME_IN_MODEL_INFERENCE = "gen_ai.latency.time_in_model_inference"


class LoadingSpanAttributes:
    """Custom attributes for code-level tracing (file, line number)."""

    CODE_NAMESPACE = "code.namespace"
    CODE_FUNCTION = "code.function"
    CODE_FILEPATH = "code.filepath"
    CODE_LINENO = "code.lineno"


def contains_trace_headers(headers: Mapping[str, str]) -> bool:
    """Check if the provided headers dictionary contains trace context."""
    return any(h in headers for h in TRACE_HEADERS)


def extract_trace_headers(headers: Mapping[str, str]) -> Mapping[str, str]:
    """
    Extract only trace-related headers from a larger header dictionary.
    Useful for logging or passing context to a non-OTel client.
    """
    return {h: headers[h] for h in TRACE_HEADERS if h in headers}


def contains_kvfabric_hint_headers(headers: Mapping[str, str]) -> bool:
    """Check if the request carries KVFabric scheduler/cache hints."""
    return any(_header_get(headers, h) is not None for h in KVFABRIC_HINT_HEADERS)


def extract_kvfabric_hint_headers(headers: Mapping[str, str]) -> Mapping[str, str]:
    """Extract KVFabric hint headers using canonical lower-case names."""
    output: dict[str, str] = {}
    for name in KVFABRIC_HINT_HEADERS:
        value = _header_get(headers, name)
        if value is not None:
            output[name] = value
    return output


@run_once
def log_tracing_disabled_warning() -> None:
    logger.warning("Received a request with trace context but tracing is disabled")
