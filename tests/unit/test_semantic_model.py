"""Tests for semantic_model — context summaries for the LLM planner."""

from __future__ import annotations

from cad_dxf_agent.core.semantic_model import build_compact_context, build_planner_context


class TestBuildPlannerContext:
    def test_has_required_keys(self, sample_context):
        """Planner context dict has all expected top-level keys."""
        ctx = build_planner_context(sample_context)
        assert "file_path" in ctx
        assert "entity_count" in ctx
        assert "layers" in ctx
        assert "entities" in ctx
        assert "blocks" in ctx

    def test_entity_count_matches(self, sample_context):
        """Entity count in context matches DrawingContext.entity_count."""
        ctx = build_planner_context(sample_context)
        assert ctx["entity_count"] == sample_context.entity_count
        assert len(ctx["entities"]) == sample_context.entity_count

    def test_entities_have_handles(self, sample_context):
        """Each entity in the planner context has a handle."""
        ctx = build_planner_context(sample_context)
        for entity in ctx["entities"]:
            assert "handle" in entity
            assert entity["handle"]  # Non-empty

    def test_layers_have_protected_flag(self, sample_context):
        """Layer entries include a protected flag."""
        ctx = build_planner_context(sample_context)
        protected_names = {layer["name"] for layer in ctx["layers"] if layer["protected"]}
        assert "TITLE" in protected_names


class TestBuildCompactContext:
    def test_compact_has_summary_header(self, sample_context):
        """Compact context starts with DRAWING SUMMARY."""
        compact = build_compact_context(sample_context)
        assert compact.startswith("DRAWING SUMMARY:")

    def test_compact_has_entity_count(self, sample_context):
        """Compact context includes total entity count."""
        compact = build_compact_context(sample_context)
        assert f"Total entities: {sample_context.entity_count}" in compact

    def test_compact_marks_protected_layers(self, sample_context):
        """Protected layers are marked with (PROTECTED) in compact context."""
        compact = build_compact_context(sample_context)
        assert "(PROTECTED)" in compact

    def test_compact_includes_blocks(self, sample_context):
        """Compact context lists available blocks."""
        compact = build_compact_context(sample_context)
        assert "COLUMN_MARK" in compact

    def test_compact_has_tool_instructions(self, sample_context):
        """Compact context ends with tool-use instructions."""
        compact = build_compact_context(sample_context)
        assert "find_entities()" in compact
        assert "Do NOT guess entity handles" in compact
