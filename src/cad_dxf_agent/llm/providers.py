"""LLM provider interface — abstract base for planner backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.ops_schema import ChangeSet


class PlannerProvider(ABC):
    """Abstract base class for LLM planner providers."""

    @abstractmethod
    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        """Generate a structured changeset from a user prompt and drawing context.

        Args:
            prompt: The user's natural-language edit request.
            drawing_context: JSON-serializable drawing context from semantic_model.

        Returns:
            A validated ChangeSet with structured operations.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and display."""
        ...

    @property
    def requires_api_key(self) -> bool:
        """Whether this provider requires an API key to function."""
        return True
