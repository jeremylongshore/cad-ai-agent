"""Shared fixtures for web backend tests."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")
from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture
def auth_user():
    """Default authenticated user dict for tests."""
    return {"uid": "test-user-123", "email": "test@example.com"}


@pytest.fixture
def client(auth_user):
    """TestClient with auth dependency overridden to return auth_user."""
    from web.backend.main import app, get_user

    async def _override_get_user():
        return auth_user

    app.dependency_overrides[get_user] = _override_get_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    """TestClient with real auth (will reject requests without valid token).

    Explicitly removes any get_user override so auth is actually enforced,
    even if a previous test's fixture teardown hasn't run yet.
    """
    from web.backend.main import app, get_user

    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    # Double-check: get_user must NOT be overridden
    assert get_user not in app.dependency_overrides
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    # Restore previous overrides (don't clobber other fixtures' state)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


@pytest.fixture
def dev_mode_client():
    """TestClient with CAD_WEB_DEV_MODE=1 (auth bypassed by the app itself)."""
    from web.backend.main import app

    app.dependency_overrides.clear()
    old = os.environ.get("CAD_WEB_DEV_MODE")
    os.environ["CAD_WEB_DEV_MODE"] = "1"
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        if old is None:
            os.environ.pop("CAD_WEB_DEV_MODE", None)
        else:
            os.environ["CAD_WEB_DEV_MODE"] = old
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
        return (
            struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw_data = zlib.compress(b"\x00\xff\x00\x00")
    return (
        sig
        + _make_chunk(b"IHDR", ihdr)
        + _make_chunk(b"IDAT", raw_data)
        + _make_chunk(b"IEND", b"")
    )


@pytest.fixture(autouse=True)
def clean_sessions():
    """Reset the session manager between tests."""
    from web.backend.main import session_mgr

    yield
    for sid in list(session_mgr._sessions.keys()):
        session_mgr.delete(sid)


@pytest.fixture
def real_pdf_bytes() -> bytes:
    """Create a real PDF with geometry for upload tests (uses fpdf2)."""
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf2 not installed")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_line_width(0.5)
    pdf.line(10, 10, 100, 10)
    pdf.line(10, 10, 10, 100)
    pdf.rect(20, 20, 60, 40)
    pdf.set_font("Helvetica", size=12)
    pdf.text(30, 50, "Test Label")
    return bytes(pdf.output())
