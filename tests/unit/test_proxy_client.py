"""Tests for proxy client provider."""

from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# New tests — _proxy_generate HTTP error handling
# ---------------------------------------------------------------------------


def _make_proxy(mock_settings) -> ProxyAgentProvider:
    """Helper: create a ProxyAgentProvider with test settings."""
    mock_settings.proxy_url = "http://localhost:8080"
    mock_settings.license_key = "test-key"
    mock_settings.gemini_model = "gemini-2.5-flash"
    return ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test-key")


def test_proxy_generate_http_error_500():
    """_proxy_generate raises RuntimeError on HTTP 500."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    http_err = urllib.error.HTTPError(
        url="http://localhost:8080/v1/generate",
        code=500,
        msg="Internal Server Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b"server blew up"),
    )
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(RuntimeError, match="Proxy returned 500"),
    ):
        p._proxy_generate([{"role": "user", "parts": [{"text": "hi"}]}], [])


def test_proxy_generate_http_error_401():
    """_proxy_generate raises RuntimeError on HTTP 401 (auth failure)."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    http_err = urllib.error.HTTPError(
        url="http://localhost:8080/v1/generate",
        code=401,
        msg="Unauthorized",
        hdrs={},  # type: ignore[arg-type]
        fp=None,
    )
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(RuntimeError, match="Proxy returned 401"),
    ):
        p._proxy_generate([{"role": "user", "parts": [{"text": "hi"}]}], [])


def test_proxy_generate_success():
    """_proxy_generate returns parsed JSON on HTTP 200."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    expected_payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}}]}
    raw_body = b'{"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}}]}'
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = raw_body

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = p._proxy_generate([{"role": "user", "parts": [{"text": "hi"}]}], [])

    assert result == expected_payload


# ---------------------------------------------------------------------------
# _build_initial_prompt
# ---------------------------------------------------------------------------


def test_build_initial_prompt_without_image():
    """_build_initial_prompt includes user request in output."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    ctx = {
        "entities": [],
        "layers": [],
        "blocks": [],
        "file_path": "drawing.dxf",
    }
    prompt = p._build_initial_prompt("Move column A", ctx)
    assert "Move column A" in prompt
    assert "USER REQUEST" in prompt


def test_build_initial_prompt_with_image(tmp_path):
    """_build_initial_prompt includes vision description when image_path is set."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    p._image_path = str(tmp_path / "dummy.png")
    ctx = {
        "entities": [],
        "layers": [],
        "blocks": [],
        "file_path": "drawing.dxf",
    }
    mock_target = "cad_dxf_agent.llm.proxy_client.describe_drawing_mock"
    with patch(mock_target, return_value="A structural drawing"):
        prompt = p._build_initial_prompt("Rotate beam", ctx)

    assert "Rotate beam" in prompt
    assert "DRAWING VISUAL DESCRIPTION" in prompt
    assert "A structural drawing" in prompt


# ---------------------------------------------------------------------------
# _reconstruct_context — bad entity handling
# ---------------------------------------------------------------------------


def test_reconstruct_context_skips_bad_entities():
    """_reconstruct_context silently skips entities with missing required keys."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    drawing_context = {
        "file_path": "test.dxf",
        "entities": [
            # Valid entity
            {
                "handle": "A1",
                "type": "LINE",
                "layer": "STRUCTURAL",
                "insert_point": {"x": 0.0, "y": 0.0},
            },
            # Missing "handle" — should be skipped (KeyError)
            {
                "type": "LINE",
                "layer": "STRUCTURAL",
            },
            # Unknown entity_type — should be skipped (ValueError)
            {
                "handle": "B2",
                "type": "WIPEOUT",  # Not in EntityType enum
                "layer": "STRUCTURAL",
            },
        ],
        "layers": [{"name": "STRUCTURAL", "protected": False}],
        "blocks": [],
    }

    ctx = p._reconstruct_context(drawing_context)
    # Only the valid entity should survive
    assert len(ctx.entities) == 1
    assert ctx.entities[0].handle == "A1"


def test_reconstruct_context_handles_missing_insert_point():
    """_reconstruct_context creates entity without insert_point when absent."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        p = _make_proxy(ms)

    drawing_context = {
        "file_path": "test.dxf",
        "entities": [
            {
                "handle": "C3",
                "type": "TEXT",
                "layer": "NOTES",
                # No insert_point key
                "text": "Some note",
            }
        ],
        "layers": [{"name": "NOTES", "protected": False}],
        "blocks": [],
    }

    ctx = p._reconstruct_context(drawing_context)
    assert len(ctx.entities) == 1
    assert ctx.entities[0].insert_point is None
    assert ctx.entities[0].text_content == "Some note"


# ---------------------------------------------------------------------------
# plan() with conversation_history
# ---------------------------------------------------------------------------


def test_proxy_plan_with_conversation_history(sample_drawing_context):
    """plan() forwards conversation history into the initial contents list."""
    with patch("cad_dxf_agent.llm.proxy_client.settings") as ms:
        ms.proxy_url = "http://localhost:8080"
        ms.license_key = "test-key"
        ms.gemini_model = "gemini-2.5-flash"
        ms.protected_layers = ["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]
        p = ProxyAgentProvider(proxy_url="http://localhost:8080", license_key="test-key")

    captured_contents: list = []

    def mock_generate(contents, tools):
        captured_contents.extend(contents)
        # Return immediately with no function calls → loop exits
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": "Done."}]}}]}

    p._proxy_generate = mock_generate  # type: ignore[assignment]

    history = [
        {"role": "user", "text": "Prior user turn"},
        {"role": "assistant", "text": "Prior model response"},
    ]
    p.plan("New request", sample_drawing_context, conversation_history=history)

    # First call contents should include the two history entries + current prompt
    assert len(captured_contents) >= 3
    roles = [c["role"] for c in captured_contents]
    assert "user" in roles
