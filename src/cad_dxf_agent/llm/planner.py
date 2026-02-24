"""Planner — orchestrates prompt-to-changeset flow via provider backends."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from ..models.ops_schema import ChangeSet
from ..models.trace_schema import PlannerTrace
from ..otel import get_tracer
from ..settings import settings
from .errors import PlannerRetryExhaustedError, PlannerTimeoutError
from .mock_provider import MockProvider
from .providers import PlannerProvider

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def get_provider(provider_name: str | None = None) -> PlannerProvider:
    """Get the configured planner provider.

    Defaults to mock provider if no provider is configured or if CAD_LLM_PROVIDER=mock.
    """
    name = (provider_name or settings.llm_provider).lower()

    if name == "mock":
        return MockProvider()

    if name in ("gemini", "google", "vertex"):
        try:
            from .gemini_provider import GeminiProvider

            return GeminiProvider()
        except ImportError:
            logger.warning(
                "google-cloud-aiplatform not installed, falling back to mock. "
                "Install with: pip install google-cloud-aiplatform"
            )
            return MockProvider()

    if name == "agent":
        try:
            from .agent_provider import AgentProvider

            return AgentProvider()
        except ImportError:
            logger.warning(
                "google-cloud-aiplatform not installed, falling back to mock-agent. "
                "Install with: pip install google-cloud-aiplatform"
            )
            from .agent_provider import MockAgentProvider

            return MockAgentProvider()

    if name == "mock-agent":
        from .agent_provider import MockAgentProvider

        return MockAgentProvider()

    if name in ("proxy", "proxy-agent"):
        try:
            from .proxy_client import ProxyAgentProvider

            return ProxyAgentProvider()
        except ValueError as e:
            logger.warning("Proxy provider misconfigured (%s), falling back to mock-agent", e)
            from .agent_provider import MockAgentProvider

            return MockAgentProvider()

    logger.warning("Unknown provider '%s', falling back to mock", name)
    return MockProvider()


def _call_with_timeout(
    provider: PlannerProvider,
    prompt: str,
    drawing_context: dict,
    timeout: int,
) -> ChangeSet:
    """Call provider.plan() with a wall-clock timeout."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(provider.plan, prompt, drawing_context)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            raise PlannerTimeoutError(timeout) from exc


def run_planner(
    prompt: str,
    drawing_context: dict,
    provider: PlannerProvider | None = None,
) -> ChangeSet:
    """Run the planner to generate a changeset from a user prompt.

    Tries deterministic planning first for obvious operations.
    Falls back to the LLM provider with timeout and retry logic.

    Args:
        prompt: Natural-language edit request from the user.
        drawing_context: Drawing context dict from semantic_model.build_planner_context().
        provider: Optional override for the planner provider.

    Returns:
        Validated ChangeSet with structured operations.

    Raises:
        PlannerTimeoutError: If the planner exceeds wall-clock timeout.
        PlannerRetryExhaustedError: If all retry attempts fail.
    """
    with tracer.start_as_current_span("cad.run_planner") as span:
        if provider is None:
            provider = get_provider()

        # Try deterministic planner first (no LLM call needed)
        from .deterministic_planner import deterministic_plan

        det_result = deterministic_plan(prompt, drawing_context)
        if det_result is not None:
            span.set_attribute("cad.mode", "deterministic")
            span.set_attribute("cad.ops.count", det_result.op_count)
            logger.info(
                "Deterministic plan used (%d ops) for prompt: %s",
                det_result.op_count,
                prompt[:80],
            )
            det_result.planner_trace = PlannerTrace(
                provider_name="deterministic",
                total_turns=0,
                total_duration_ms=0.0,
                deterministic=True,
            )
            return det_result

        span.set_attribute("cad.mode", provider.name)
        logger.info("Running planner [%s] for prompt: %s", provider.name, prompt[:80])

        timeout = settings.planner_timeout
        max_retries = settings.planner_max_retries
        retry_delay = settings.planner_retry_delay
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                changeset = _call_with_timeout(provider, prompt, drawing_context, timeout)
                span.set_attribute("cad.ops.count", changeset.op_count)
                span.set_attribute("cad.planner.attempt", attempt)
                logger.info(
                    "Planner returned %d operation(s) on attempt %d for prompt: %s",
                    changeset.op_count,
                    attempt,
                    prompt[:80],
                )
                return changeset
            except PlannerTimeoutError:
                raise  # Timeout is not retryable
            except Exception as exc:
                last_error = exc
                logger.warning("Planner attempt %d/%d failed: %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.info("Retrying in %.1fs...", delay)
                    time.sleep(delay)

        raise PlannerRetryExhaustedError(max_retries, last_error)
