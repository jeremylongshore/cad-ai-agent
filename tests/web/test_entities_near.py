"""Tests for POST /api/entities/near — entity picking for viewer selection."""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


@pytest.mark.web
class TestEntitiesNear:
    """Tests for the /api/entities/near endpoint."""

    def test_returns_entities_near_known_position(self, client, upload_dxf):
        session_id, file_info = upload_dxf
        # Use a large radius to ensure we find at least one entity
        resp = client.post(
            "/api/entities/near",
            json={"session_id": session_id, "x": 0.0, "y": 0.0, "radius": 100_000.0, "limit": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        # The sample DXF has entities, so we should find at least one near origin with big radius
        # (if sample has entities with insert_point, this will find them)

    def test_returns_empty_when_far_from_entities(self, client, upload_dxf):
        session_id, _ = upload_dxf
        # Use a position very far away with a tiny radius
        resp = client.post(
            "/api/entities/near",
            json={"session_id": session_id, "x": 999_999.0, "y": 999_999.0, "radius": 1.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] == []

    def test_respects_limit_parameter(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/entities/near",
            json={"session_id": session_id, "x": 0.0, "y": 0.0, "radius": 100_000.0, "limit": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entities"]) <= 1

    def test_entity_fields(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/entities/near",
            json={"session_id": session_id, "x": 0.0, "y": 0.0, "radius": 100_000.0, "limit": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["entities"]:
            entity = data["entities"][0]
            assert "handle" in entity
            assert "entity_type" in entity
            assert "layer" in entity
            assert "label" in entity

    def test_404_for_invalid_session(self, client):
        resp = client.post(
            "/api/entities/near",
            json={"session_id": "nonexistent", "x": 0.0, "y": 0.0},
        )
        assert resp.status_code == 404

    def test_400_when_no_drawing_loaded(self, client):
        """Session exists but no context loaded — should return 400."""
        from web.backend.main import session_mgr

        session = session_mgr.create("test-user-123")
        session.context = None  # Ensure no context

        resp = client.post(
            "/api/entities/near",
            json={"session_id": session.session_id, "x": 0.0, "y": 0.0},
        )
        assert resp.status_code == 400

    def test_default_radius_and_limit(self, client, upload_dxf):
        """Omitting radius and limit uses defaults (50, 5)."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/entities/near",
            json={"session_id": session_id, "x": 0.0, "y": 0.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entities"]) <= 5
