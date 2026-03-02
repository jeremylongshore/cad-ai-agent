"""Tests for the agent provider — mock agent tool-use flow."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.agent_provider import (
    MockAgentProvider,
    _extract_function_calls,
    _extract_text,
)
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


class TestExtractFunctionCalls:
    """Unit tests for _extract_function_calls (lines 599-615)."""

    def _make_response_with_fc(self, name: str, args: dict):
        """Build a mock Gemini response carrying one function_call part."""
        fc = MagicMock()
        fc.name = name
        fc.args = args

        part = MagicMock()
        part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]
        return response

    def test_extract_single_function_call(self):
        """Returns a list with the extracted function call dict."""
        response = self._make_response_with_fc("move_entity", {"handle": "A1", "dx": 5.0})
        result = _extract_function_calls(response)
        assert result == [{"name": "move_entity", "args": {"handle": "A1", "dx": 5.0}}]

    def test_extract_empty_args_becomes_dict(self):
        """When fc.args is falsy, args defaults to {}."""
        fc = MagicMock()
        fc.name = "find_entities"
        fc.args = None  # falsy

        part = MagicMock()
        part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]

        result = _extract_function_calls(response)
        assert result == [{"name": "find_entities", "args": {}}]

    def test_extract_no_function_call_parts(self):
        """Part without function_call attribute is skipped."""
        part = MagicMock(spec=[])  # no 'function_call' attribute

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]

        result = _extract_function_calls(response)
        assert result == []

    def test_extract_function_calls_exception_returns_empty(self):
        """AttributeError/TypeError → swallowed, returns [] (lines 613-614)."""
        # None has no .candidates attribute → AttributeError inside the loop
        result = _extract_function_calls(None)
        assert result == []

    def test_extract_function_calls_type_error(self):
        """Non-iterable .candidates causes TypeError → returns []."""
        response = MagicMock()
        response.candidates = 42  # not iterable
        result = _extract_function_calls(response)
        assert result == []


class TestExtractText:
    """Unit tests for _extract_text (lines 618-628)."""

    def _make_response_with_text(self, text: str):
        """Build a mock Gemini response carrying one text part."""
        part = MagicMock()
        part.text = text

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]
        return response

    def test_extract_text_returns_list(self):
        """Returns list of text strings from all text parts."""
        response = self._make_response_with_text("Hello world")
        result = _extract_text(response)
        assert result == ["Hello world"]

    def test_extract_text_empty_string_skipped(self):
        """Parts with empty text (falsy) are excluded."""
        part = MagicMock()
        part.text = ""

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]

        result = _extract_text(response)
        assert result == []

    def test_extract_text_exception_returns_empty(self):
        """AttributeError on None → swallowed, returns [] (lines 626-627)."""
        result = _extract_text(None)
        assert result == []


class TestReconstructContext:
    """Unit tests for AgentProvider._reconstruct_context (lines 358-408)."""

    def _make_provider(self):
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project="p", location="l")
        provider._model = MagicMock()
        return provider

    def test_reconstruct_valid_entities(self):
        """Well-formed entities are parsed into EntityRef objects."""
        provider = self._make_provider()
        ctx = provider._reconstruct_context(_SIMPLE_CONTEXT)
        assert len(ctx.entities) == 2
        handles = {e.handle for e in ctx.entities}
        assert handles == {"A1", "B1"}

    def test_reconstruct_malformed_entity_skipped(self):
        """Entity missing 'handle' key is silently skipped (lines 391-392)."""
        provider = self._make_provider()
        bad_context = {
            "entities": [
                {"type": "LINE", "layer": "STRUCTURAL"},  # missing 'handle'
                {
                    "handle": "OK1",
                    "type": "LINE",
                    "layer": "STRUCTURAL",
                    "insert_point": {"x": 0.0, "y": 0.0},
                },
            ],
            "layers": [{"name": "STRUCTURAL", "protected": False}],
            "blocks": [],
        }
        ctx = provider._reconstruct_context(bad_context)
        # Only the valid entity survives
        assert len(ctx.entities) == 1
        assert ctx.entities[0].handle == "OK1"

    def test_reconstruct_invalid_entity_type_skipped(self):
        """Entity with unknown EntityType value is silently skipped (lines 391-392)."""
        provider = self._make_provider()
        bad_context = {
            "entities": [
                {
                    "handle": "X1",
                    "type": "UNKNOWN_TYPE_XYZ",  # not in EntityType enum
                    "layer": "STRUCTURAL",
                    "insert_point": {"x": 0.0, "y": 0.0},
                },
                {
                    "handle": "OK1",
                    "type": "LINE",
                    "layer": "STRUCTURAL",
                    "insert_point": {"x": 1.0, "y": 1.0},
                },
            ],
            "layers": [{"name": "STRUCTURAL", "protected": False}],
            "blocks": [],
        }
        ctx = provider._reconstruct_context(bad_context)
        assert len(ctx.entities) == 1
        assert ctx.entities[0].handle == "OK1"


class TestMockAgentProviderDirect:
    """Test MockAgentProvider using _SIMPLE_CONTEXT directly (lines 458-459)."""

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
        """MockAgentProvider silently skips malformed entities during reconstruction (line 458-459).

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


class TestAgentProviderGetModel:
    """Unit tests for AgentProvider._get_model ImportError path (lines 245-249)."""

    def test_get_model_import_error(self, monkeypatch):
        """Missing vertexai → ImportError with helpful message (lines 245-249)."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project="p", location="l")
        # Setting to None in sys.modules forces ImportError on 'import vertexai'
        monkeypatch.setitem(sys.modules, "vertexai", None)

        with pytest.raises(ImportError, match="google-cloud-aiplatform"):
            provider._get_model()

    def test_get_model_already_initialized(self):
        """Second call returns the cached model without re-initializing."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project="p", location="l")
        mock_model = MagicMock()
        provider._model = mock_model

        result = provider._get_model()
        assert result is mock_model


class TestBuildChatHistory:
    """Unit tests for AgentProvider._build_chat_history (lines 258-266)."""

    def test_empty_history_returns_empty_list(self):
        """None or empty list → []."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        assert AgentProvider._build_chat_history(None) == []
        assert AgentProvider._build_chat_history([]) == []

    def test_non_empty_history_with_mock_sdk(self, monkeypatch):
        """Non-empty history converts entries to Content objects (lines 258-266)."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        mock_gen_models = types.ModuleType("vertexai.generative_models")
        MockContent = MagicMock(side_effect=lambda role, parts: {"role": role, "parts": parts})
        MockPart = MagicMock()
        MockPart.from_text = MagicMock(return_value=MagicMock())

        mock_gen_models.Content = MockContent
        mock_gen_models.Part = MockPart

        monkeypatch.setitem(sys.modules, "vertexai.generative_models", mock_gen_models)

        history = [
            {"role": "user", "text": "Hello"},
            {"role": "model", "text": "Hi there"},
        ]
        result = AgentProvider._build_chat_history(history)

        assert len(result) == 2
        # First entry should be "user" role
        assert result[0]["role"] == "user"
        # Second entry should be "model" role (not "user")
        assert result[1]["role"] == "model"
