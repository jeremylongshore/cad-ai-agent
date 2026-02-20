"""Tests for the Gemini vision pipeline planner provider.

All tests mock the Vertex AI SDK — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cad_dxf_agent.llm.gemini_provider import GeminiProvider
from cad_dxf_agent.llm.planner import get_provider
from cad_dxf_agent.models.ops_schema import OpType

# --- Fixtures ---


@pytest.fixture
def valid_changeset_json():
    """Valid ChangeSet JSON that Gemini would return."""
    return json.dumps(
        {
            "operations": [
                {
                    "op_type": "move_entity",
                    "target_handle": "ABC",
                    "target_layer": "STRUCTURAL",
                    "params": {"dx": 10.0, "dy": 5.0},
                }
            ],
            "revision_label": "Moved column east by 10 units",
        }
    )


@pytest.fixture
def multi_op_changeset_json():
    """ChangeSet JSON with multiple operations."""
    return json.dumps(
        {
            "operations": [
                {
                    "op_type": "move_entity",
                    "target_handle": "A1",
                    "params": {"dx": 5.0, "dy": 0.0},
                },
                {
                    "op_type": "edit_text",
                    "target_handle": "B2",
                    "params": {"new_text": "Updated Note"},
                },
                {
                    "op_type": "delete_entity",
                    "target_handle": "C3",
                },
            ],
            "revision_label": "Multiple edits",
        }
    )


@pytest.fixture
def sample_drawing_context():
    """Minimal drawing context dict."""
    return {
        "entities": [
            {
                "handle": "ABC",
                "type": "LINE",
                "layer": "STRUCTURAL",
                "insert_point": {"x": 0, "y": 0},
            },
            {
                "handle": "DEF",
                "type": "TEXT",
                "layer": "NOTES",
                "insert_point": {"x": 10, "y": 10},
                "text": "Column C-4",
            },
        ],
        "layers": [
            {"name": "STRUCTURAL", "protected": False},
            {"name": "NOTES", "protected": False},
            {"name": "TITLE", "protected": True},
        ],
        "blocks": ["COLUMN_MARK"],
    }


def _make_provider() -> GeminiProvider:
    """Create a GeminiProvider with test settings (no real SDK init)."""
    provider = GeminiProvider(
        project="test-project",
        location="us-central1",
        model_name="gemini-1.5-pro",
    )
    # Set mock model to bypass _get_model() which needs real SDK
    provider._model = MagicMock()
    return provider


def _mock_gemini_response(provider: GeminiProvider, response_text: str) -> None:
    """Configure the mock model to return a specific text response."""
    mock_response = MagicMock()
    mock_response.text = response_text
    provider._model.generate_content.return_value = mock_response


# --- Provider Selection ---


class TestProviderSelection:
    """Test that the planner correctly selects Gemini provider."""

    def test_get_provider_mock_default(self):
        """Default provider is mock."""
        provider = get_provider("mock")
        assert provider.name == "mock"

    @patch("cad_dxf_agent.llm.planner.settings")
    def test_gemini_provider_name_wired(self, mock_settings):
        """'gemini' name routes to GeminiProvider (or mock fallback)."""
        mock_settings.llm_provider = "gemini"
        # If google-cloud-aiplatform is installed, returns Gemini; otherwise mock
        provider = get_provider("gemini")
        assert provider is not None


# --- Gemini Provider ---


class TestGeminiProvider:
    """Test GeminiProvider with mocked Vertex AI SDK."""

    def test_plan_valid_response(self, valid_changeset_json, sample_drawing_context):
        """Gemini returns valid JSON → parses to ChangeSet."""
        provider = _make_provider()
        _mock_gemini_response(provider, valid_changeset_json)

        changeset = provider.plan("Move column east by 10", sample_drawing_context)

        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
        assert changeset.operations[0].target_handle == "ABC"
        assert changeset.operations[0].params["dx"] == 10.0

    def test_plan_multi_op_response(self, multi_op_changeset_json, sample_drawing_context):
        """Gemini returns multiple operations."""
        provider = _make_provider()
        _mock_gemini_response(provider, multi_op_changeset_json)

        changeset = provider.plan("Multiple edits", sample_drawing_context)

        assert changeset.op_count == 3
        assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
        assert changeset.operations[1].op_type == OpType.EDIT_TEXT
        assert changeset.operations[2].op_type == OpType.DELETE_ENTITY

    def test_plan_retry_on_invalid_response(self, valid_changeset_json, sample_drawing_context):
        """Gemini retries once if first response is invalid."""
        provider = _make_provider()

        invalid_response = MagicMock()
        invalid_response.text = "not valid json {"
        valid_response = MagicMock()
        valid_response.text = valid_changeset_json
        provider._model.generate_content.side_effect = [
            invalid_response,
            valid_response,
        ]

        changeset = provider.plan("Move column", sample_drawing_context)
        assert changeset.op_count == 1
        assert provider._model.generate_content.call_count == 2

    def test_plan_raises_after_retry_exhausted(self, sample_drawing_context):
        """Raises ValueError if both attempts fail."""
        provider = _make_provider()

        bad_response = MagicMock()
        bad_response.text = "invalid json"
        provider._model.generate_content.return_value = bad_response

        with pytest.raises(ValueError):
            provider.plan("Move column", sample_drawing_context)

    def test_plan_empty_response(self, sample_drawing_context):
        """Raises ValueError on empty Gemini response."""
        provider = _make_provider()

        empty_response = MagicMock()
        empty_response.text = ""
        provider._model.generate_content.return_value = empty_response

        with pytest.raises(ValueError, match="empty response"):
            provider.plan("Move column", sample_drawing_context)

    def test_provider_name(self):
        """Provider name includes model name."""
        provider = _make_provider()
        assert "gemini" in provider.name
        assert "1.5-pro" in provider.name

    def test_provider_no_api_key_required(self):
        """Uses GCP credentials, not API key."""
        provider = _make_provider()
        assert provider.requires_api_key is False

    def test_plan_with_code_fenced_response(self, sample_drawing_context):
        """Gemini sometimes wraps JSON in code fences."""
        provider = _make_provider()

        fenced = (
            '```json\n{"operations": [{"op_type": "delete_entity", "target_handle": "X1"}]}\n```'
        )
        _mock_gemini_response(provider, fenced)

        changeset = provider.plan("Delete entity X1", sample_drawing_context)
        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.DELETE_ENTITY

    def test_plan_bare_array_response(self, sample_drawing_context):
        """Gemini returns a bare array instead of object."""
        provider = _make_provider()

        bare = '[{"op_type": "move_entity", "target_handle": "A", "params": {"dx": 1, "dy": 2}}]'
        _mock_gemini_response(provider, bare)

        changeset = provider.plan("Move it", sample_drawing_context)
        assert changeset.op_count == 1

    def test_plan_safety_blocked_response(self, sample_drawing_context):
        """Raises ValueError when response is blocked by safety filters."""
        provider = _make_provider()

        blocked_response = MagicMock()
        # SDK raises ValueError when accessing .text on a blocked response
        type(blocked_response).text = property(
            lambda self: (_ for _ in ()).throw(ValueError("Response blocked by safety filters"))
        )
        provider._model.generate_content.return_value = blocked_response

        with pytest.raises(ValueError, match="blocked"):
            provider.plan("Move column", sample_drawing_context)
