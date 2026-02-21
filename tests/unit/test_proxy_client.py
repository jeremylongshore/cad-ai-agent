"""Tests for proxy client provider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cad_dxf_agent.llm.proxy_client import ProxyAgentProvider


@pytest.fixture
def sample_drawing_context():
    """Minimal drawing context dict."""
    return {
        "file_path": "test.dxf",
        "entity_count": 2,
        "layers": [
            {"name": "STRUCTURAL", "protected": False, "entity_count": 1},
            {"name": "TITLE", "protected": True, "entity_count": 1},
        ],
        "entities": [
            {
                "handle": "A1",
                "type": "LINE",
                "layer": "STRUCTURAL",
                "space": "Model",
                "insert_point": {"x": 0.0, "y": 0.0},
                "text": None,
                "block_name": None,
            },
            {
                "handle": "A2",
                "type": "TEXT",
                "layer": "TITLE",
                "space": "Model",
                "insert_point": {"x": 10.0, "y": 10.0},
                "text": "Title Block",
                "block_name": None,
            },
        ],
        "blocks": [],
        "layouts": [{"name": "Model", "entity_count": 2}],
        "unsupported_types": [],
    }


def test_proxy_requires_url():
    """ProxyAgentProvider raises ValueError without proxy URL."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = None
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        with pytest.raises(ValueError, match="CAD_PROXY_URL"):
            ProxyAgentProvider(proxy_url="", license_key="test")


def test_proxy_provider_name():
    """Name includes model name."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = "http://localhost:8080"
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test")
        assert "proxy-agent" in p.name
        assert "gemini-2.5-flash" in p.name


def test_proxy_no_api_key_needed():
    """Proxy provider doesn't require API key."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = "http://localhost:8080"
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test")
        assert not p.requires_api_key


def test_extract_function_calls():
    """Extract function calls from proxy response JSON."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = "http://localhost:8080"
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test")

    response = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "function_call": {
                                "name": "find_entities",
                                "args": {"layer": "STRUCTURAL"},
                            }
                        }
                    ],
                }
            }
        ]
    }

    calls = p._extract_function_calls(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "find_entities"
    assert calls[0]["args"]["layer"] == "STRUCTURAL"


def test_extract_no_function_calls():
    """Empty response yields no function calls."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = "http://localhost:8080"
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test")

    response = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": "Done editing."}],
                }
            }
        ]
    }
    calls = p._extract_function_calls(response)
    assert len(calls) == 0


def test_proxy_plan_with_mock_responses(sample_drawing_context):
    """Proxy plan processes tool calls and returns ChangeSet."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as mock_settings:
        mock_settings.proxy_url = "http://localhost:8080"
        mock_settings.license_key = "test"
        mock_settings.gemini_model = "gemini-2.5-flash"
        mock_settings.protected_layers = ["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]

        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test")

        # Mock _proxy_generate to return a tool call, then a text-only response
        call_count = [0]

        def mock_generate(contents, tools):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "function_call": {
                                            "name": "move_entity",
                                            "args": {
                                                "handle": "A1",
                                                "dx": 24.0,
                                                "dy": 0.0,
                                            },
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Done."}],
                        }
                    }
                ]
            }

        p._proxy_generate = mock_generate  # type: ignore[assignment]
        result = p.plan("Move footing east", sample_drawing_context)

        assert result.op_count == 1
        assert result.operations[0].op_type.value == "move_entity"
        assert result.operations[0].params["dx"] == 24.0


def test_planner_routes_proxy():
    """Planner factory recognizes 'proxy' provider name."""
    from cad_dxf_agent.llm.planner import get_provider

    with patch("cad_dxf_agent.llm.planner.settings") as mock_settings:
        mock_settings.llm_provider = "proxy"

    # Without CAD_PROXY_URL, falls back to mock-agent
    provider = get_provider("proxy")
    assert "mock-agent" in provider.name


def test_planner_routes_proxy_agent():
    """Planner factory recognizes 'proxy-agent' provider name."""
    from cad_dxf_agent.llm.planner import get_provider

    provider = get_provider("proxy-agent")
    assert "mock-agent" in provider.name
