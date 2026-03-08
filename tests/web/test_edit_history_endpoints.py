"""Tests for undo/redo/snapshot/history endpoints (EPIC-CAD-27)."""

from __future__ import annotations

from pathlib import Path

import pytest

starlette = pytest.importorskip("starlette", reason="web tests require fastapi/starlette")

from fastapi.testclient import TestClient  # noqa: E402

from tests.helpers.dxf_factory import create_structural_drawing  # noqa: E402


@pytest.fixture()
def client():
    """Create a test client with dev mode enabled."""
    import os

    old = os.environ.get("CAD_WEB_DEV_MODE")
    os.environ["CAD_WEB_DEV_MODE"] = "1"
    from web.backend.main import app

    with TestClient(app) as c:
        yield c
    if old is None:
        os.environ.pop("CAD_WEB_DEV_MODE", None)
    else:
        os.environ["CAD_WEB_DEV_MODE"] = old


@pytest.fixture()
def session_with_dxf(client: TestClient, tmp_path: Path):
    """Upload a DXF and return the session_id."""
    dxf_path = create_structural_drawing(tmp_path)
    with open(dxf_path, "rb") as f:
        resp = client.post("/api/upload", files={"file": ("test.dxf", f)})
    assert resp.status_code == 200
    return resp.json()["session_id"]


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestHistoryEndpoint:
    def test_history_returns_200(self, client, session_with_dxf):
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        assert resp.status_code == 200

    def test_history_initial_state(self, client, session_with_dxf):
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        data = resp.json()
        assert data["current_index"] == -1
        assert data["can_undo"] is False
        assert data["can_redo"] is False
        assert len(data["entries"]) == 1  # Just "initial"
        assert data["entries"][0]["label"] == "initial"

    def test_history_invalid_session(self, client):
        resp = client.get("/api/history", params={"session_id": "nonexistent"})
        assert resp.status_code == 404

    def test_history_depth_zero_at_start(self, client, session_with_dxf):
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        assert resp.json()["depth"] == 0


# ---------------------------------------------------------------------------
# POST /api/undo
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestUndoEndpoint:
    def test_undo_at_initial_returns_nothing_to_undo(self, client, session_with_dxf):
        resp = client.post(
            "/api/undo",
            json={"session_id": session_with_dxf},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["undone"] is False
        assert "nothing to undo" in data["message"].lower()

    def test_undo_invalid_session(self, client):
        resp = client.post("/api/undo", json={"session_id": "nonexistent"})
        assert resp.status_code == 404

    def test_undo_has_state_fields(self, client, session_with_dxf):
        resp = client.post(
            "/api/undo",
            json={"session_id": session_with_dxf},
        )
        data = resp.json()
        assert "can_undo" in data
        assert "can_redo" in data
        assert "current_label" in data
        assert "depth" in data


# ---------------------------------------------------------------------------
# POST /api/redo
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestRedoEndpoint:
    def test_redo_at_latest_returns_nothing_to_redo(self, client, session_with_dxf):
        resp = client.post(
            "/api/redo",
            json={"session_id": session_with_dxf},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["redone"] is False
        assert "nothing to redo" in data["message"].lower()

    def test_redo_invalid_session(self, client):
        resp = client.post("/api/redo", json={"session_id": "nonexistent"})
        assert resp.status_code == 404

    def test_redo_has_state_fields(self, client, session_with_dxf):
        resp = client.post(
            "/api/redo",
            json={"session_id": session_with_dxf},
        )
        data = resp.json()
        assert "can_undo" in data
        assert "can_redo" in data
        assert "current_label" in data
        assert "depth" in data


# ---------------------------------------------------------------------------
# POST /api/snapshot
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestSnapshotEndpoint:
    def test_snapshot_creates_entry(self, client, session_with_dxf):
        resp = client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf, "label": "before-walls"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "before-walls"
        assert data["depth"] == 1

    def test_snapshot_default_label(self, client, session_with_dxf):
        resp = client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf},
        )
        data = resp.json()
        assert "snapshot" in data["label"]

    def test_snapshot_appears_in_history(self, client, session_with_dxf):
        client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf, "label": "my-save"},
        )
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        data = resp.json()
        assert data["depth"] == 1
        labels = [e["label"] for e in data["entries"]]
        assert "my-save" in labels

    def test_snapshot_enables_undo(self, client, session_with_dxf):
        client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf, "label": "checkpoint"},
        )
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        assert resp.json()["can_undo"] is True

    def test_snapshot_invalid_session(self, client):
        resp = client.post(
            "/api/snapshot",
            json={"session_id": "nonexistent", "label": "test"},
        )
        assert resp.status_code == 404

    def test_multiple_snapshots(self, client, session_with_dxf):
        for label in ["alpha", "beta", "gamma"]:
            client.post(
                "/api/snapshot",
                json={"session_id": session_with_dxf, "label": label},
            )
        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        data = resp.json()
        assert data["depth"] == 3
        labels = [e["label"] for e in data["entries"]]
        assert "alpha" in labels
        assert "beta" in labels
        assert "gamma" in labels


# ---------------------------------------------------------------------------
# Undo/Redo round-trip
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestUndoRedoRoundTrip:
    def test_snapshot_then_undo_then_redo(self, client, session_with_dxf):
        # Create a snapshot
        client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf, "label": "v1"},
        )

        # Undo should succeed
        resp = client.post("/api/undo", json={"session_id": session_with_dxf})
        data = resp.json()
        assert data["undone"] is True
        assert data["current_label"] == "initial"
        assert data["can_undo"] is False
        assert data["can_redo"] is True

        # Redo should succeed
        resp = client.post("/api/redo", json={"session_id": session_with_dxf})
        data = resp.json()
        assert data["redone"] is True
        assert data["current_label"] == "v1"
        assert data["can_undo"] is True
        assert data["can_redo"] is False

    def test_undo_redo_preserves_history_depth(self, client, session_with_dxf):
        for label in ["a", "b", "c"]:
            client.post(
                "/api/snapshot",
                json={"session_id": session_with_dxf, "label": label},
            )

        # Undo twice
        client.post("/api/undo", json={"session_id": session_with_dxf})
        client.post("/api/undo", json={"session_id": session_with_dxf})

        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        data = resp.json()
        assert data["current_label"] == "a"
        assert data["can_undo"] is True
        assert data["can_redo"] is True

    def test_new_snapshot_after_undo_truncates_redo(self, client, session_with_dxf):
        for label in ["a", "b", "c"]:
            client.post(
                "/api/snapshot",
                json={"session_id": session_with_dxf, "label": label},
            )

        # Undo to "b"
        client.post("/api/undo", json={"session_id": session_with_dxf})

        # Create new snapshot — should truncate "c"
        client.post(
            "/api/snapshot",
            json={"session_id": session_with_dxf, "label": "d"},
        )

        resp = client.get("/api/history", params={"session_id": session_with_dxf})
        data = resp.json()
        labels = [e["label"] for e in data["entries"]]
        assert "c" not in labels
        assert "d" in labels
        assert data["can_redo"] is False
