"""Tests for settings — environment-based configuration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


class TestSettings:
    def test_default_provider_is_mock(self):
        """Default LLM provider is 'mock'."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
            assert s.llm_provider == "mock"

    def test_custom_protected_layers(self):
        """Custom protected layers are parsed and uppercased."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {"CAD_PROTECTED_LAYERS": "foo, bar, baz"}, clear=True):
            s = Settings()
            assert s.protected_layers == ["FOO", "BAR", "BAZ"]

    def test_revision_notes_disabled(self):
        """Revision notes can be disabled via env var."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {"CAD_REVISION_NOTES_ENABLED": "false"}, clear=True):
            s = Settings()
            assert s.revision_notes_enabled is False

    def test_data_dir(self):
        """data_dir points to ~/.cad-dxf-agent."""
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.data_dir == Path.home() / ".cad-dxf-agent"

    def test_get_api_key_known_provider(self):
        """get_api_key returns the env var value for known providers."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {"CAD_GEMINI_API_KEY": "test-key-123"}, clear=True):
            s = Settings()
            assert s.get_api_key("gemini-key") == "test-key-123"

    def test_generic_key_falls_back_for_known_provider(self):
        """The portable key works when a provider-specific key is absent."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {"CAD_LLM_API_KEY": "portable-key"}, clear=True):
            s = Settings()
            assert s.get_api_key("gemini-key") == "portable-key"

    def test_get_api_key_unknown_provider(self):
        """Unknown providers use the generic BYOK key when configured."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(os.environ, {"CAD_LLM_API_KEY": "portable-key"}, clear=True):
            s = Settings()
            assert s.get_api_key("unknown_provider") == "portable-key"

    def test_provider_neutral_model_and_endpoint(self):
        """Shared model and endpoint settings are available to custom providers."""
        from cad_dxf_agent.settings import Settings

        with patch.dict(
            os.environ,
            {
                "CAD_LLM_MODEL": "local-model",
                "CAD_LLM_API_KEY": "portable-key",
                "CAD_LLM_BASE_URL": "http://localhost:8080/v1",
            },
            clear=True,
        ):
            s = Settings()
            assert s.llm_model == "local-model"
            assert s.llm_api_key == "portable-key"
            assert s.llm_base_url == "http://localhost:8080/v1"
