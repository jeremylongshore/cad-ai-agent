"""Tests for the mock agent provider — tool-use flow without a real LLM."""

from __future__ import annotations

from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.agent_provider import MockAgentProvider
from cad_dxf_agent.llm.planner import get_provider


class TestMockAgentProvider:
    """Test the mock agent provider that simulates tool-use without a real LLM."""

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


class TestGetProvider:
    """The planner factory routes 'mock-agent' to MockAgentProvider."""

    def test_mock_agent_provider(self):
        provider = get_provider("mock-agent")
        assert isinstance(provider, MockAgentProvider)


# ---------------------------------------------------------------------------
# Shared context fixture for low-level unit tests
# ---------------------------------------------------------------------------

_SIMPLE_CONTEXT = {
    "entities": [
        {
            "handle": "A1",
            "type": "LINE",
            "layer": "STRUCTURAL",
            "insert_point": {"x": 0.0, "y": 0.0},
        },
        {
            "handle": "B1",
            "type": "TEXT",
            "layer": "NOTES",
            "insert_point": {"x": 10.0, "y": 10.0},
            "text": "Label",
        },
    ],
    "layers": [
        {"name": "STRUCTURAL", "protected": False},
        {"name": "NOTES", "protected": False},
        {"name": "TITLE", "protected": True},
    ],
    "blocks": [],
}


class TestMockAgentProviderDirect:
    """Test MockAgentProvider using _SIMPLE_CONTEXT directly."""

    def test_move_prompt_direct_context(self):
        """Move prompt picks first non-protected entity and moves it."""
        provider = MockAgentProvider()
        changeset = provider.plan("Move the beam east", _SIMPLE_CONTEXT)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "move_entity"
        assert changeset.operations[0].params["dx"] == 24.0

    def test_delete_prompt_direct_context(self):
        """Delete prompt deletes first non-protected entity."""
        provider = MockAgentProvider()
        # Note: "Remove" contains "move" so use "Delete" to avoid the move branch
        changeset = provider.plan("Delete this entity", _SIMPLE_CONTEXT)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "delete_entity"

    def test_text_prompt_direct_context(self):
        """Text prompt edits first TEXT/MTEXT entity."""
        provider = MockAgentProvider()
        changeset = provider.plan("Edit the text label", _SIMPLE_CONTEXT)
        assert changeset.op_count >= 1
        assert changeset.operations[0].op_type == "edit_text"

    def test_default_prompt_direct_context(self):
        """Unrecognised prompt falls back to move with dx=12, dy=12."""
        provider = MockAgentProvider()
        changeset = provider.plan("Do something interesting", _SIMPLE_CONTEXT)
        assert changeset.op_count >= 1
        op = changeset.operations[0]
        assert op.op_type == "move_entity"
        assert op.params["dx"] == 12.0
        assert op.params["dy"] == 12.0

    def test_malformed_entity_in_context_skipped(self):
        """MockAgentProvider silently skips malformed entities during reconstruction.

        The (KeyError, ValueError): continue guard in the entity reconstruction loop
        prevents bad entity dicts from crashing the provider. We put the valid entity
        first so the provider successfully acts on it, then verify the changeset is produced.
        """
        context_with_bad = {
            "entities": [
                {
                    "handle": "G1",
                    "type": "LINE",
                    "layer": "STRUCTURAL",
                    "insert_point": {"x": 5.0, "y": 5.0},
                },
                {"type": "LINE", "layer": "STRUCTURAL"},  # no handle — skipped in reconstruction
            ],
            "layers": [{"name": "STRUCTURAL", "protected": False}],
            "blocks": [],
        }
        provider = MockAgentProvider()
        # Should not raise — the bad entity is skipped during EntityRef reconstruction
        changeset = provider.plan("Move everything", context_with_bad)
        assert changeset.op_count >= 1
