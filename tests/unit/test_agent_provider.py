"""Tests for the agent provider — mock agent tool-use flow."""

from __future__ import annotations

from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.agent_provider import MockAgentProvider
from cad_dxf_agent.llm.planner import get_provider


class TestMockAgentProvider:
    """Test the mock agent provider that simulates tool-use without Gemini."""

    def test_provider_name(self):
        provider = MockAgentProvider()
        assert provider.name == "mock-agent"

    def test_no_api_key_required(self):
        provider = MockAgentProvider()
        assert provider.requires_api_key is False

    def test_move_prompt(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Move the footing east", ctx)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "move_entity"
        assert changeset.operations[0].params["dx"] == 24.0

    def test_delete_prompt(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Delete this entity", ctx)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "delete_entity"

    def test_text_prompt(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Change the text label", ctx)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "edit_text"

    def test_default_prompt(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Do something with the drawing", ctx)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "move_entity"

    def test_protected_layer_not_targeted(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Move something", ctx)
        for op in changeset.operations:
            if op.target_layer:
                assert op.target_layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")

    def test_revision_label_set(self, sample_context):
        provider = MockAgentProvider()
        ctx = build_planner_context(sample_context)
        changeset = provider.plan("Move the column", ctx)
        assert changeset.revision_label is not None
        assert "Mock agent" in changeset.revision_label


class TestCompactContext:
    """Test that agent uses compact context instead of full entity JSON."""

    def test_initial_prompt_is_compact(self, sample_context):
        """Initial prompt should NOT contain full entity JSON."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        ctx = build_planner_context(sample_context)
        summary = AgentProvider._build_compact_summary(ctx)
        assert "DRAWING SUMMARY:" in summary
        assert "Total entities:" in summary
        assert "Do NOT guess entity handles" in summary
        # Should NOT contain raw entity handles
        for e in ctx.get("entities", []):
            assert e["handle"] not in summary

    def test_compact_context_includes_layer_summary(self, sample_context):
        """Compact context includes layer names and counts."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        ctx = build_planner_context(sample_context)
        summary = AgentProvider._build_compact_summary(ctx)
        assert "STRUCTURAL" in summary
        assert "NOTES" in summary
        assert "PROTECTED" in summary  # TITLE layer is protected

    def test_compact_context_includes_blocks(self, sample_context):
        """Compact context lists available blocks."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        ctx = build_planner_context(sample_context)
        summary = AgentProvider._build_compact_summary(ctx)
        assert "COLUMN_MARK" in summary


class TestGetProvider:
    """Test that the planner factory routes to agent providers."""

    def test_mock_agent_provider(self):
        provider = get_provider("mock-agent")
        assert isinstance(provider, MockAgentProvider)

    def test_agent_provider_falls_back(self):
        # Without google-cloud-aiplatform installed in test env,
        # should fall back to MockAgentProvider
        provider = get_provider("agent")
        assert provider is not None


class TestVisionDescriber:
    """Test the mock vision describer."""

    def test_mock_description(self):
        from cad_dxf_agent.llm.vision_describer import describe_drawing_mock

        desc = describe_drawing_mock()
        assert "foundation plan" in desc.lower()
        assert "grid" in desc.lower()

    def test_mock_description_with_path(self):
        from cad_dxf_agent.llm.vision_describer import describe_drawing_mock

        desc = describe_drawing_mock("/some/fake/path.png")
        assert len(desc) > 50
