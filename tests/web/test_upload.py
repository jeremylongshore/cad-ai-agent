"""Tests for POST /api/upload endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

    def test_upload_pdf_converts_and_succeeds(self, client):
        """Mock the converter to simulate successful PDF->DXF conversion."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_path = None  # Will be set in the test

        def fake_convert(upload_path):
            # Create a minimal DXF at the expected location
            import ezdxf

            doc = ezdxf.new()
            msp = doc.modelspace()
            msp.add_line((0, 0), (10, 10))
            out = upload_path.parent / "converted.dxf"
            doc.saveas(str(out))
            mock_result.output_path = out
            return mock_result

        with patch("cad_dxf_agent.core.converter.convert_to_dxf", side_effect=fake_convert):
            resp = client.post(
                "/api/upload",
                files={"file": ("plan.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 200
        assert "session_id" in resp.json()

    def test_upload_pdf_conversion_failure(self, client):
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Unsupported PDF format"

        with patch("cad_dxf_agent.core.converter.convert_to_dxf", return_value=mock_result):
            resp = client.post(
                "/api/upload",
                files={"file": ("plan.pdf", b"%PDF-1.4 bad", "application/pdf")},
            )
        assert resp.status_code == 422
        assert "Conversion failed" in resp.json()["detail"]

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
            files={"file": ("broken.dxf", b"this is not a dxf file at all", "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert "Failed to read DXF" in resp.json()["detail"]

    def test_upload_requires_auth(self, unauth_client, sample_dxf_bytes):
        resp = unauth_client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 401
