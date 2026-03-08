"""Tests for StrategyRegistry — maps classification to stage pipelines."""

import pytest

from cad_dxf_agent.llm.strategy_registry import StrategyRegistry
from cad_dxf_agent.models.objective_schema import (
    ObjectiveTag,
    RequestClass,
    StagePipelineDefinition,
)


@pytest.fixture
def registry():
    return StrategyRegistry()


class TestDefaultLookup:
    """Every RequestClass has a default pipeline."""

    @pytest.mark.parametrize("request_class", list(RequestClass))
    def test_all_classes_have_defaults(self, registry, request_class):
        pipeline = registry.lookup(request_class)
        assert isinstance(pipeline, StagePipelineDefinition)
        assert len(pipeline.stages) > 0

    def test_understand_is_direct(self, registry):
        p = registry.lookup(RequestClass.UNDERSTAND)
        assert p.output_mode == "direct"
        assert "analyze" in p.stages

    def test_modify_has_preview(self, registry):
        p = registry.lookup(RequestClass.MODIFY)
        assert "preview" in p.stages

    def test_optimize_is_staged(self, registry):
        p = registry.lookup(RequestClass.OPTIMIZE)
        assert p.output_mode == "staged"

    def test_validate_has_validate_stage(self, registry):
        p = registry.lookup(RequestClass.VALIDATE)
        assert "validate" in p.stages


class TestTagOverrides:
    """Tag-specific overrides refine the default pipeline."""

    def test_cost_reduction_override(self, registry):
        p = registry.lookup(RequestClass.OPTIMIZE, ObjectiveTag.COST_REDUCTION)
        assert "quantify" in p.stages
        assert "recommend" in p.stages

    def test_space_count_override(self, registry):
        p = registry.lookup(RequestClass.ESTIMATE, ObjectiveTag.SPACE_COUNT)
        assert "detect_zones" in p.stages

    def test_contractor_summary_override(self, registry):
        p = registry.lookup(RequestClass.SUMMARIZE, ObjectiveTag.CONTRACTOR_COMMUNICATION)
        assert "quantify" in p.stages

    def test_reviewer_summary_has_validate(self, registry):
        p = registry.lookup(RequestClass.SUMMARIZE, ObjectiveTag.REVIEWER_COMMUNICATION)
        assert "validate" in p.stages

    def test_missing_items_override(self, registry):
        p = registry.lookup(RequestClass.VALIDATE, ObjectiveTag.MISSING_ITEMS)
        assert "validate" in p.stages

    def test_no_override_falls_to_default(self, registry):
        p = registry.lookup(RequestClass.UNDERSTAND, ObjectiveTag.AESTHETICS)
        # No override for understand × aesthetics — should get default
        default = registry.lookup(RequestClass.UNDERSTAND)
        assert p.stages == default.stages


class TestCustomRegistration:
    """Custom overrides and defaults can be registered."""

    def test_register_override(self, registry):
        custom = StagePipelineDefinition(
            stages=["custom_stage"],
            output_mode="direct",
            description="Custom pipeline",
        )
        registry.register_override(RequestClass.UNDERSTAND, ObjectiveTag.AESTHETICS, custom)
        p = registry.lookup(RequestClass.UNDERSTAND, ObjectiveTag.AESTHETICS)
        assert p.stages == ["custom_stage"]

    def test_register_default(self, registry):
        custom = StagePipelineDefinition(
            stages=["a", "b", "c"],
            output_mode="full",
        )
        registry.register_default(RequestClass.UNDERSTAND, custom)
        p = registry.lookup(RequestClass.UNDERSTAND)
        assert p.stages == ["a", "b", "c"]


class TestRegistryProperties:
    """Registry exposes its configuration."""

    def test_all_defaults_populated(self, registry):
        defaults = registry.all_defaults
        assert len(defaults) == 8  # one per RequestClass

    def test_all_overrides_populated(self, registry):
        overrides = registry.all_overrides
        assert len(overrides) >= 10  # at least 10 tag-specific overrides
