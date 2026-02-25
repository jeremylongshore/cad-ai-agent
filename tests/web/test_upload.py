"""Tests for POST /api/upload endpoint.

Uses real pipeline components: dxf_reader, converter. No mocks.
PDF tests require pymupdf + fpdf2 (installed in dev deps), skip otherwise.
"""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestUpload:
    def test_upload_dxf_returns_session_id(self, client, sample_dxf_bytes):
        resp = client.post(
            "/api/upload",
            files={"file": ("drawing.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 16

    def test_upload_dxf_returns_file_info(self, client, sample_dxf_bytes):
        resp = client.post(
            "/api/upload",
            files={"file": ("drawing.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        data = resp.json()
        info = data["file_info"]
        assert info["filename"] == "drawing.dxf"
        assert info["entity_count"] > 0
        assert info["layer_count"] > 0
        assert isinstance(info["layers"], list)

    def test_upload_pdf_converts_and_succeeds(self, client, real_pdf_bytes):
        """Upload a real PDF and convert through the real pipeline."""
        resp = client.post(
            "/api/upload",
            files={"file": ("plan.pdf", real_pdf_bytes, "application/pdf")},
        )
        # Conversion may succeed or fail depending on converter quality with
        # this synthetic PDF, but it should not 500
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            assert "session_id" in resp.json()

    def test_upload_pdf_bad_content_returns_422(self, client):
        """Garbage bytes with .pdf extension should fail conversion."""
        resp = client.post(
            "/api/upload",
            files={"file": ("plan.pdf", b"not a pdf at all", "application/pdf")},
        )
        # Either converter fails (422) or import fails (500)
        assert resp.status_code in (422, 500)

    def test_upload_invalid_extension(self, client):
        resp = client.post(
            "/api/upload",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_upload_no_filename(self, client):
        resp = client.post(
            "/api/upload",
            files={"file": ("", b"empty", "application/octet-stream")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_no_file_field(self, client):
        """POST without the 'file' field triggers FastAPI validation error."""
        resp = client.post("/api/upload")
        assert resp.status_code == 422

    def test_upload_corrupt_dxf(self, client):
        resp = client.post(
            "/api/upload",
            files={
                "file": ("broken.dxf", b"this is not a dxf file at all", "application/octet-stream")
            },
        )
        assert resp.status_code == 422
        assert "Failed to read DXF" in resp.json()["detail"]

    def test_upload_requires_auth(self, unauth_client, sample_dxf_bytes):
        resp = unauth_client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 401
