"""Tests for v2 preview/approve/apply endpoints (EPIC-CAD-08).

Uses shared fixtures from conftest.py (client, upload_dxf, etc.)
"""

from __future__ import annotations

import ezdxf
import pytest


@pytest.fixture
def uploaded_session(client, tmp_path):
    """Upload a DXF with known entities and return session_id."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_text(
        "Test Label",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )
    block = doc.blocks.new("COLUMN_MARK")
    block.add_circle((0, 0), radius=2)
    msp.add_blockref("COLUMN_MARK", insert=(50, 50), dxfattribs={"layer": "STRUCTURAL"})

    dxf_path = tmp_path / "test.dxf"
    doc.saveas(str(dxf_path))

    with open(dxf_path, "rb") as f:
        files = {"file": ("test.dxf", f, "application/octet-stream")}
        resp = client.post("/api/upload", files=files)
    assert resp.status_code == 200
    return resp.json()["session_id"]


@pytest.fixture
def session_with_plan(client, uploaded_session):
    """Send a prompt to create an edit plan in the session."""
    resp = client.post(
        "/api/v2/prompt",
        json={"session_id": uploaded_session, "prompt": "move the line 10 units right"},
    )
    assert resp.status_code == 200
    return uploaded_session


# --- Preview endpoint tests ---


def test_preview_invalid_session(client):
    resp = client.post("/api/v2/preview", json={"session_id": "nonexistent"})
    assert resp.status_code == 404


def test_preview_no_plan(client, uploaded_session):
    resp = client.post("/api/v2/preview", json={"session_id": uploaded_session})
    assert resp.status_code == 400
    assert "No edit plan" in resp.json()["detail"]


def test_preview_returns_structured_preview(client, session_with_plan):
    resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "preview_edit"
    assert data["task_family"] == "edit_plan"
    assert "data" in data
    assert "preview_id" in data["data"]
    assert "total_actions" in data["data"]


# --- Approve endpoint tests ---


def test_approve_invalid_session(client):
    resp = client.post(
        "/api/v2/approve",
        json={"session_id": "nonexistent", "plan_id": "abc", "approved": True},
    )
    assert resp.status_code == 404


def test_approve_no_plan(client, uploaded_session):
    resp = client.post(
        "/api/v2/approve",
        json={"session_id": uploaded_session, "plan_id": "abc", "approved": True},
    )
    assert resp.status_code == 400


def test_approve_plan_id_mismatch(client, session_with_plan):
    resp = client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": "wrong_id", "approved": True},
    )
    assert resp.status_code == 400
    assert "mismatch" in resp.json()["detail"].lower()


def test_approve_records_decision(client, session_with_plan):
    # Get plan_id from preview
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    plan_id = preview_resp.json()["data"]["plan_id"]

    resp = client.post(
        "/api/v2/approve",
        json={
            "session_id": session_with_plan,
            "plan_id": plan_id,
            "approved": True,
            "notes": "Looks good",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["plan_id"] == plan_id
    assert data["event_type"] == "approval_granted"


def test_approve_rejection(client, session_with_plan):
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    plan_id = preview_resp.json()["data"]["plan_id"]

    resp = client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": plan_id, "approved": False},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "approval_rejected"


# --- Apply endpoint tests ---


def test_apply_invalid_session(client):
    resp = client.post("/api/v2/apply", json={"session_id": "nonexistent"})
    assert resp.status_code == 404


def test_apply_no_plan(client, uploaded_session):
    resp = client.post("/api/v2/apply", json={"session_id": uploaded_session})
    assert resp.status_code == 400


def test_apply_without_approval_rejected(client, session_with_plan):
    """Apply without prior approval → rejected (plan requires approval by default)."""
    resp = client.post("/api/v2/apply", json={"session_id": session_with_plan})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == "rejected"


def test_apply_with_approval_succeeds(client, session_with_plan):
    """Full flow: preview → approve → apply."""
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    plan_id = preview_resp.json()["data"]["plan_id"]

    client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": plan_id, "approved": True},
    )

    resp = client.post("/api/v2/apply", json={"session_id": session_with_plan})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "applied_edit"
    assert data["task_family"] == "apply_edit"
    assert data["data"]["status"] in ("success", "partial", "failed", "rejected")


def test_apply_response_format(client, session_with_plan):
    """Verify response includes expected fields."""
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    plan_id = preview_resp.json()["data"]["plan_id"]

    client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": plan_id, "approved": True},
    )

    resp = client.post("/api/v2/apply", json={"session_id": session_with_plan})
    data = resp.json()

    assert "message" in data
    assert "operations" in data
    assert "data" in data
    assert "apply_id" in data["data"]
    assert "success_count" in data["data"]
    assert "failure_count" in data["data"]


# --- Integration flow tests ---


def test_preview_then_apply_full_flow(client, session_with_plan):
    """Integration: preview → approve → apply → correct response types."""
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    assert preview_resp.status_code == 200
    assert preview_resp.json()["response_type"] == "preview_edit"

    plan_id = preview_resp.json()["data"]["plan_id"]
    assert plan_id is not None

    approve_resp = client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": plan_id, "approved": True},
    )
    assert approve_resp.status_code == 200

    apply_resp = client.post("/api/v2/apply", json={"session_id": session_with_plan})
    assert apply_resp.status_code == 200
    assert apply_resp.json()["response_type"] == "applied_edit"


def test_preview_after_rejection_still_works(client, session_with_plan):
    """Can re-preview after rejecting."""
    preview_resp = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    plan_id = preview_resp.json()["data"]["plan_id"]

    client.post(
        "/api/v2/approve",
        json={"session_id": session_with_plan, "plan_id": plan_id, "approved": False},
    )

    preview_resp2 = client.post("/api/v2/preview", json={"session_id": session_with_plan})
    assert preview_resp2.status_code == 200
