"""Tests for GeminiKeyProvider — API key auth via google-generativeai SDK.

All tests mock the google.generativeai module — no real API calls are made.
"""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from cad_dxf_agent.llm.gemini_key_provider import GeminiKeyProvider
from cad_dxf_agent.models.ops_schema import OpType

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

VALID_CHANGESET = json.dumps(
    {
        "operations": [
            {
                "op_type": "move_entity",
                "target_handle": "ABC",
                "target_layer": "STRUCTURAL",
                "params": {"dx": 10.0, "dy": 5.0},
            }
        ],
        "revision_label": "Moved column",
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
        ],
        "layers": [
            {"name": "STRUCTURAL", "protected": False},
        ],
        "blocks": [],
    }


@pytest.fixture
def mock_genai(monkeypatch):
    """Inject a fully-mocked google.generativeai module into sys.modules."""
    # Build a minimal module tree so `import google.generativeai` succeeds
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.generativeai")
    genai_mod.configure = MagicMock()
    genai_mod.GenerativeModel = MagicMock()
    genai_types = types.ModuleType("google.generativeai.types")
    genai_types.GenerationConfig = MagicMock(return_value=MagicMock())
    genai_mod.types = genai_types

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.generativeai.types", genai_types)
    return genai_mod


def _make_provider(mock_genai) -> GeminiKeyProvider:
    """Create a GeminiKeyProvider with a pre-wired mock model."""
    provider = GeminiKeyProvider(model_name="gemini-test-model")
    provider._model = MagicMock()
    return provider


def _set_response(provider: GeminiKeyProvider, text: str) -> None:
    """Configure the mock model's generate_content to return *text*."""
    mock_resp = MagicMock()
    mock_resp.text = text
    provider._model.generate_content.return_value = mock_resp


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


class TestGeminiKeyProviderMetadata:
    def test_name_includes_model(self, mock_genai):
        provider = _make_provider(mock_genai)
        assert "gemini-key" in provider.name
        assert "gemini-test-model" in provider.name

    def test_requires_api_key(self, mock_genai):
        provider = _make_provider(mock_genai)
        assert provider.requires_api_key is True


# ---------------------------------------------------------------------------
# _get_model()
# ---------------------------------------------------------------------------


class TestGetModel:
    def test_get_model_import_error(self):
        """_get_model raises ImportError when google-generativeai is absent."""
        provider = GeminiKeyProvider(model_name="gemini-test-model")

        # Patch builtins.__import__ so that importing 'google.generativeai'
        # raises ImportError, regardless of what is actually installed.
        real_import = __import__

        def _failing_import(name, *args, **kwargs):
            if name == "google.generativeai":
                raise ImportError("Simulated missing package")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_failing_import),
            pytest.raises(ImportError, match="google-generativeai"),
        ):
            provider._get_model()

    def test_get_model_missing_api_key(self, mock_genai, monkeypatch):
        """_get_model raises ValueError when CAD_GEMINI_API_KEY is not set."""
        monkeypatch.delenv("CAD_GEMINI_API_KEY", raising=False)

        with patch("cad_dxf_agent.llm.gemini_key_provider.settings") as mock_settings:
            mock_settings.gemini_model = "gemini-test-model"
            mock_settings.gemini_max_retries = 1
            mock_settings.get_api_key.return_value = None
            mock_settings.llm_temperature = 0.0
            mock_settings.llm_top_p = None
            mock_settings.llm_top_k = None
            mock_settings.llm_max_output_tokens = 4096

            provider = GeminiKeyProvider(model_name="gemini-test-model")
            with pytest.raises(ValueError, match="CAD_GEMINI_API_KEY"):
                provider._get_model()

    def test_get_model_successful_init(self, mock_genai):
        """_get_model configures genai and returns a model instance."""
        mock_model_instance = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance

        with patch("cad_dxf_agent.llm.gemini_key_provider.settings") as mock_settings:
            mock_settings.gemini_model = "gemini-test-model"
            mock_settings.gemini_max_retries = 1
            mock_settings.get_api_key.return_value = "fake-api-key"
            mock_settings.llm_temperature = 0.0
            mock_settings.llm_top_p = None
            mock_settings.llm_top_k = None
            mock_settings.llm_max_output_tokens = 4096

            provider = GeminiKeyProvider(model_name="gemini-test-model")
            model = provider._get_model()

        mock_genai.configure.assert_called_once_with(api_key="fake-api-key")
        assert mock_genai.GenerativeModel.called
        assert model is mock_model_instance

    def test_get_model_cached(self, mock_genai):
        """_get_model returns cached model on second call without re-init."""
        provider = _make_provider(mock_genai)
        first = provider._get_model()
        second = provider._get_model()
        assert first is second
        # GenerativeModel constructor should never be called — model was pre-seeded
        mock_genai.GenerativeModel.assert_not_called()


# ---------------------------------------------------------------------------
# plan() — single-turn (no conversation history)
# ---------------------------------------------------------------------------


class TestPlanSingleTurn:
    def test_plan_valid_response(self, mock_genai, sample_drawing_context):
        """Single-turn plan returns a valid ChangeSet."""
        provider = _make_provider(mock_genai)
        _set_response(provider, VALID_CHANGESET)

        changeset = provider.plan("Move column east by 10", sample_drawing_context)

        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
        assert changeset.operations[0].target_handle == "ABC"
        assert changeset.operations[0].params["dx"] == 10.0
        # Uses generate_content, not start_chat
        provider._model.generate_content.assert_called_once()
        provider._model.start_chat.assert_not_called()

    def test_plan_retry_on_invalid_response(self, mock_genai, sample_drawing_context):
        """plan() retries once when first response is unparseable."""
        provider = _make_provider(mock_genai)
        provider._max_retries = 1

        bad_resp = MagicMock()
        bad_resp.text = "not valid json {"
        good_resp = MagicMock()
        good_resp.text = VALID_CHANGESET
        provider._model.generate_content.side_effect = [bad_resp, good_resp]

        changeset = provider.plan("Move column", sample_drawing_context)
        assert changeset.op_count == 1
        assert provider._model.generate_content.call_count == 2

    def test_plan_raises_when_max_retries_zero(self, mock_genai, sample_drawing_context):
        """With max_retries=0, ValueError propagates immediately on bad response."""
        provider = _make_provider(mock_genai)
        provider._max_retries = 0
        _set_response(provider, "totally invalid json {{{{")

        with pytest.raises(ValueError):
            provider.plan("Move column", sample_drawing_context)

        # Only one call — no retry
        assert provider._model.generate_content.call_count == 1


# ---------------------------------------------------------------------------
# plan() — multi-turn (with conversation_history)
# ---------------------------------------------------------------------------


class TestPlanMultiTurn:
    def test_plan_with_conversation_history_uses_chat(self, mock_genai, sample_drawing_context):
        """Multi-turn plan uses _chat_generate (start_chat + send_message)."""
        provider = _make_provider(mock_genai)

        # Set up the mock chat session
        mock_chat = MagicMock()
        mock_chat_resp = MagicMock()
        mock_chat_resp.text = VALID_CHANGESET
        mock_chat.send_message.return_value = mock_chat_resp
        provider._model.start_chat.return_value = mock_chat

        history = [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hi there"},
        ]

        changeset = provider.plan("Move column east", sample_drawing_context, history)

        assert changeset.op_count == 1
        provider._model.start_chat.assert_called_once()
        mock_chat.send_message.assert_called_once()
        # generate_content should NOT be called for multi-turn
        provider._model.generate_content.assert_not_called()

    def test_chat_generate_maps_roles(self, mock_genai):
        """_chat_generate converts assistant role to 'model' for Gemini."""
        provider = _make_provider(mock_genai)

        mock_chat = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "response text"
        mock_chat.send_message.return_value = mock_resp
        provider._model.start_chat.return_value = mock_chat

        history = [
            {"role": "user", "text": "Hi"},
            {"role": "assistant", "text": "Hello"},
        ]

        result = provider._chat_generate(provider._model, history, "new prompt")

        call_kwargs = provider._model.start_chat.call_args
        passed_history = call_kwargs[1]["history"] if call_kwargs[1] else call_kwargs[0][0]
        # "assistant" should be mapped to "model"
        roles = [h["role"] for h in passed_history]
        assert "user" in roles
        assert "model" in roles
        assert "assistant" not in roles
        assert result == "response text"
