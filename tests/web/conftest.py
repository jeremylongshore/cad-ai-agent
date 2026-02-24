"""Shared fixtures for web backend tests."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_user():
    """Default authenticated user dict for tests."""
    return {"uid": "test-user-123", "email": "test@example.com"}


@pytest.fixture
def client(auth_user):
    """TestClient with auth dependency overridden to return auth_user."""
    from web.backend.main import app, get_user

    async def _mock_get_user():
        return auth_user

    app.dependency_overrides[get_user] = _mock_get_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    """TestClient with real auth (will reject requests without valid token)."""
    from web.backend.main import app

    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def dev_mode_client():
    """TestClient with CAD_WEB_DEV_MODE=1 (auth bypassed by the app itself)."""
    from web.backend.main import app

    app.dependency_overrides.clear()
    with patch.dict(os.environ, {"CAD_WEB_DEV_MODE": "1"}):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_dxf_bytes(sample_dxf: Path) -> bytes:
    """Read sample DXF fixture as bytes for upload."""
    return sample_dxf.read_bytes()


@pytest.fixture
def upload_dxf(client, sample_dxf_bytes):
    """Upload a DXF via the client and return (session_id, file_info)."""
    resp = client.post(
        "/api/upload",
        files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data["session_id"], data["file_info"]


@pytest.fixture
def tiny_png() -> bytes:
    """Create a minimal valid 1x1 red PNG (no external deps)."""

    def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw_data = zlib.compress(b"\x00\xff\x00\x00")
    return sig + _make_chunk(b"IHDR", ihdr) + _make_chunk(b"IDAT", raw_data) + _make_chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def clean_sessions():
    """Reset the session manager between tests."""
    from web.backend.main import session_mgr

    yield
    for sid in list(session_mgr._sessions.keys()):
        session_mgr.delete(sid)


@pytest.fixture
def mock_renderer():
    """Mock the renderer to avoid matplotlib dependency in tests."""
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.success = False

    with patch("cad_dxf_agent.core.renderer.render_dxf_to_png", return_value=mock_result):
        yield mock_result
