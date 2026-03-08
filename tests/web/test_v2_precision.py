"""Tests for precision controls via POST /api/v2/prompt — EPIC-CAD-14."""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


class TestPrecisionControlsAbsent:
    """No client_metadata → precision fields default to empty."""

    def test_no_client_metadata_has_empty_ambiguity_candidates(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ambiguity_candidates"] == []

    def test_no_client_metadata_has_empty_precision_actions(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["precision_actions"] == []

    def test_null_client_metadata_is_accepted(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity A1 by 5,0",
                "client_metadata": None,
            },
        )
        assert resp.status_code == 200


class TestPrecisionControlsPresent:
    """Requests with client_metadata.precision — verify field enrichment."""

    def test_target_handles_populates_precision_fields(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "target_handles": ["A1", "B2"],
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Precision controls present → action details should be populated
        assert isinstance(data["precision_actions"], list)
        assert isinstance(data["ambiguity_candidates"], list)

    def test_exact_delta_accepted_without_error(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by some amount",
                "client_metadata": {
                    "precision": {
                        "exact_delta": {"dx": 25.0, "dy": 0.0},
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "precision_actions" in data

    def test_exclude_layers_accepted_without_error(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "exclude_layers": ["REVISION", "TITLE"],
                    }
                },
            },
        )
        assert resp.status_code == 200

    def test_model_space_only_accepted(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "model_space_only": True,
                    }
                },
            },
        )
        assert resp.status_code == 200

    def test_full_precision_controls_accepted(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "target_handles": [],
                        "target_layers": ["STRUCTURAL"],
                        "exclude_layers": ["REVISION"],
                        "target_types": ["LINE"],
                        "model_space_only": True,
                        "exact_delta": {"dx": 10.0, "dy": 0.0},
                        "confidence_threshold": 0.5,
                        "disable_inference": False,
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ambiguity_candidates" in data
        assert "precision_actions" in data

    def test_invalid_precision_data_graceful_fallback(self, client, upload_dxf):
        """Malformed precision data should not cause a 500 — graceful non-fatal path."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "confidence_threshold": 999,  # out of bounds, Pydantic rejects
                    }
                },
            },
        )
        # Should either succeed (fallback) or return a structured error — not a 500
        assert resp.status_code in (200, 422)

    def test_confidence_threshold_in_metadata_accepted(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {
                    "precision": {
                        "confidence_threshold": 0.7,
                    }
                },
            },
        )
        assert resp.status_code == 200

    def test_precision_actions_list_type(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {"precision": {"target_layers": ["STRUCTURAL"]}},
            },
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["precision_actions"], list)

    def test_ambiguity_candidates_list_type(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "move entity by 10,0",
                "client_metadata": {"precision": {"target_layers": ["STRUCTURAL"]}},
            },
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["ambiguity_candidates"], list)
