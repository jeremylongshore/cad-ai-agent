"""Planner — orchestrates prompt-to-changeset flow via provider backends."""

from __future__ import annotations

import logging

from ..models.ops_schema import ChangeSet
from ..otel import get_tracer
from ..settings import settings
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

    logger.warning("Unknown provider '%s', falling back to mock", name)
    return MockProvider()


def run_planner(
    prompt: str,
    drawing_context: dict,
    provider: PlannerProvider | None = None,
) -> ChangeSet:
    """Run the planner to generate a changeset from a user prompt.

    Args:
        prompt: Natural-language edit request from the user.
        drawing_context: Drawing context dict from semantic_model.build_planner_context().
        provider: Optional override for the planner provider.

    Returns:
        Validated ChangeSet with structured operations.
    """
    with tracer.start_as_current_span("cad.run_planner") as span:
        if provider is None:
            provider = get_provider()

        span.set_attribute("cad.mode", provider.name)
        logger.info("Running planner [%s] for prompt: %s", provider.name, prompt[:80])

        changeset = provider.plan(prompt, drawing_context)

        span.set_attribute("cad.ops.count", changeset.op_count)
        logger.info(
            "Planner returned %d operation(s) for prompt: %s",
            changeset.op_count,
            prompt[:80],
        )
        return changeset
