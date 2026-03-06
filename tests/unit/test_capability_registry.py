"""Tests for capability registry — which task families are implemented."""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.capability_registry import CapabilityRegistry
from cad_dxf_agent.models.response_schema import TaskFamily


class TestCapabilityRegistry:
    def test_default_enables_edit_plan_and_compare(self):
        reg = CapabilityRegistry(enabled=frozenset({TaskFamily.EDIT_PLAN, TaskFamily.COMPARE}))
        assert reg.is_implemented(TaskFamily.EDIT_PLAN)
        assert reg.is_implemented(TaskFamily.COMPARE)

    def test_default_blocks_unimplemented(self):
        reg = CapabilityRegistry(enabled=frozenset({TaskFamily.EDIT_PLAN, TaskFamily.COMPARE}))
        assert not reg.is_implemented(TaskFamily.QNA)
        assert not reg.is_implemented(TaskFamily.SUMMARY)
        assert not reg.is_implemented(TaskFamily.MARKUP_INTERPRETATION)
        assert not reg.is_implemented(TaskFamily.TAKEOFF_ESTIMATE)

    def test_needs_clarification_always_implemented(self):
        reg = CapabilityRegistry(enabled=frozenset())
        assert reg.is_implemented(TaskFamily.NEEDS_CLARIFICATION)

    def test_unsupported_always_implemented(self):
        reg = CapabilityRegistry(enabled=frozenset())
        assert reg.is_implemented(TaskFamily.UNSUPPORTED)

    def test_custom_enabled_set(self):
        reg = CapabilityRegistry(
            enabled=frozenset({TaskFamily.EDIT_PLAN, TaskFamily.QNA})
        )
        assert reg.is_implemented(TaskFamily.QNA)
        assert not reg.is_implemented(TaskFamily.COMPARE)

    def test_enabled_families_property(self):
        enabled = frozenset({TaskFamily.EDIT_PLAN})
        reg = CapabilityRegistry(enabled=enabled)
        assert reg.enabled_families == enabled

    def test_unimplemented_families_excludes_meta(self):
        reg = CapabilityRegistry(enabled=frozenset({TaskFamily.EDIT_PLAN, TaskFamily.COMPARE}))
        unimplemented = reg.unimplemented_families
        assert TaskFamily.QNA in unimplemented
        assert TaskFamily.NEEDS_CLARIFICATION not in unimplemented
        assert TaskFamily.UNSUPPORTED not in unimplemented
        assert TaskFamily.EDIT_PLAN not in unimplemented

    def test_settings_override(self, monkeypatch):
        """CAD_ENABLED_TASK_FAMILIES env var overrides defaults."""
        monkeypatch.setenv("CAD_ENABLED_TASK_FAMILIES", "edit_plan,qna,summary")
        # Re-create settings to pick up env
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.enabled_task_families == "edit_plan,qna,summary"
