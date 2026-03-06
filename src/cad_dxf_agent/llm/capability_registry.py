"""Capability registry — tracks which TaskFamilies are implemented.

Unimplemented families are gated at the router level and return
unsupported_operation responses without hitting the LLM.
"""

from __future__ import annotations

from cad_dxf_agent.models.response_schema import TaskFamily

# Families that have working pipeline implementations
_DEFAULT_ENABLED: frozenset[TaskFamily] = frozenset({
    TaskFamily.EDIT_PLAN,
    TaskFamily.COMPARE,
})


class CapabilityRegistry:
    """Registry of implemented task families.

    Defaults to EDIT_PLAN and COMPARE (the two families with working pipelines).
    Can be overridden via settings or direct construction.
    """

    def __init__(self, enabled: frozenset[TaskFamily] | None = None) -> None:
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = _default_from_settings()

    def is_implemented(self, family: TaskFamily) -> bool:
        """Check if a task family has a working pipeline."""
        if family in (TaskFamily.NEEDS_CLARIFICATION, TaskFamily.UNSUPPORTED):
            return True  # meta-families always handled
        return family in self._enabled

    @property
    def enabled_families(self) -> frozenset[TaskFamily]:
        return self._enabled

    @property
    def unimplemented_families(self) -> frozenset[TaskFamily]:
        all_families = frozenset(TaskFamily)
        meta = frozenset({TaskFamily.NEEDS_CLARIFICATION, TaskFamily.UNSUPPORTED})
        return all_families - self._enabled - meta


def _default_from_settings() -> frozenset[TaskFamily]:
    """Build enabled set from CAD_ENABLED_TASK_FAMILIES env var."""
    try:
        from cad_dxf_agent.settings import settings

        raw = getattr(settings, "enabled_task_families", None)
        if raw:
            return frozenset(TaskFamily(f.strip()) for f in raw.split(",") if f.strip())
    except Exception:
        pass
    return _DEFAULT_ENABLED
