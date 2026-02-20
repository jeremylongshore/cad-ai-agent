"""Planner — orchestrates prompt-to-changeset flow via provider backends."""

from __future__ import annotations

import logging

from ..models.ops_schema import ChangeSet
from ..settings import settings
from .mock_provider import MockProvider
from .providers import PlannerProvider

logger = logging.getLogger(__name__)


def get_provider(provider_name: str | None = None) -> PlannerProvider:
    """Get the configured planner provider.

    Defaults to mock provider if no provider is configured or if CAD_LLM_PROVIDER=mock.
    """
    name = (provider_name or settings.llm_provider).lower()

    if name == "mock":
        return MockProvider()

    # Future: add real providers here
    # elif name == "openai": return OpenAIProvider(...)
    # elif name == "anthropic": return AnthropicProvider(...)

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
    if provider is None:
        provider = get_provider()

    logger.info("Running planner [%s] for prompt: %s", provider.name, prompt[:80])

    changeset = provider.plan(prompt, drawing_context)

    logger.info(
        "Planner returned %d operation(s) for prompt: %s",
        changeset.op_count,
        prompt[:80],
    )
    return changeset
