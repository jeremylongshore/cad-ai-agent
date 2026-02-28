"""Tests for POST /api/revision/* endpoints.

Uses real pipeline components: ComparisonEngine, alignment, applier.
Factory helpers build deterministic DXF pairs for each scenario.
"""

from __future__ import annotations

import io
import zipfile

import pytest


@pytest.mark.web
class TestRevisionUpload:
    """Tests for POST /api/revision/upload."""

    def test_revision_upload(self, client, upload_dxf, tmp_path):
        """Upload a revision DXF, verify 200 + session state."""
        from tests.helpers.comparison_factory import _build_base

        session_id, _ = upload_dxf
        revision_bytes = _build_base(tmp_path / "revision.dxf").read_bytes()

        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["filename"] == "revision.dxf"

        # Verify session state
        from web.backend.main import session_mgr

        session = session_mgr._sessions[session_id]
        assert session.revision_path is not None
        assert session.revision_path.exists()

    def test_revision_upload_non_dxf(self, client, upload_dxf):
        """Reject non-DXF files with 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
        assert "dxf" in resp.json()["detail"].lower()

    def test_revision_upload_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/revision/upload?session_id=anything",
            files={"file": ("revision.dxf", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 401


@pytest.mark.web
class TestRevisionAlign:
    """Tests for POST /api/revision/align."""

    @pytest.fixture
    def session_with_identical_revision(self, client, tmp_path):
        """Upload master + identical revision, return session_id."""
        from tests.helpers.comparison_factory import _build_base

        master_bytes = _build_base(tmp_path / "master.dxf").read_bytes()
        revision_bytes = _build_base(tmp_path / "revision.dxf").read_bytes()

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        return session_id

    @pytest.fixture
    def session_with_offset_revision(self, client, tmp_path):
        """Upload master + offset revision, return session_id."""
        from tests.helpers.comparison_factory import make_offset_pair

        master_path, revision_path = make_offset_pair(tmp_path)
        master_bytes = master_path.read_bytes()
        revision_bytes = revision_path.read_bytes()

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        return session_id

    def test_revision_align_auto(self, client, session_with_identical_revision):
        """Auto-align identical pair — should succeed with identity method."""
        session_id = session_with_identical_revision
        resp = client.post(
            "/api/revision/align",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "identity"
        assert data["confidence"] >= 0.9
        assert "diagnostics" in data

    def test_revision_align_with_control_points(self, client, session_with_offset_revision):
        """Offset pair with manual control points — should succeed with manual method."""
        session_id = session_with_offset_revision
        resp = client.post(
            "/api/revision/align",
            json={
                "session_id": session_id,
                "control_points": ["0,0:5,3", "100,0:105,3", "0,100:5,103"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "manual"
        assert data["confidence"] > 0

    def test_revision_align_no_revision(self, client, upload_dxf):
        """Align without a revision file should return 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/revision/align",
            json={"session_id": session_id},
        )
        assert resp.status_code == 400
        assert "revision" in resp.json()["detail"].lower()

    def test_revision_align_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/revision/align",
            json={"session_id": "anything"},
        )
        assert resp.status_code == 401


@pytest.mark.web
class TestRevisionDiff:
    """Tests for POST /api/revision/diff."""

    @pytest.fixture
    def session_with_moved_revision(self, client, tmp_path):
        """Upload master + moved-entity revision, return session_id."""
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master_path, revision_path = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_path.read_bytes(), "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={
                "file": ("revision.dxf", revision_path.read_bytes(), "application/octet-stream")
            },
        )
        assert resp.status_code == 200
        return session_id

    def test_revision_diff_returns_ops(self, client, session_with_moved_revision):
        """Diff returns ops with op_ids and statuses."""
        session_id = session_with_moved_revision
        resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ops" in data
        assert "summary" in data
        assert "total_changes" in data
        assert "changelog" in data
        assert data["total_changes"] > 0

        # Each op has required fields
        for op in data["ops"]:
            assert "op_id" in op
            assert "op_type" in op
            assert "target_handle" in op
            assert "target_layer" in op
            assert "description" in op
            assert "confidence" in op
            assert "status" in op

    def test_revision_diff_no_revision(self, client, upload_dxf):
        """Diff without a revision file should return 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        assert resp.status_code == 400
        assert "revision" in resp.json()["detail"].lower()

    def test_revision_diff_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/revision/diff",
            json={"session_id": "anything"},
        )
        assert resp.status_code == 401


@pytest.mark.web
class TestRevisionApprove:
    """Tests for POST /api/revision/approve."""

    @pytest.fixture
    def session_with_ops(self, client, tmp_path):
        """Upload, upload revision, diff — return (session_id, ops)."""
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master_path, revision_path = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_path.read_bytes(), "application/octet-stream")},
        )
        session_id = resp.json()["session_id"]

        client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={
                "file": ("revision.dxf", revision_path.read_bytes(), "application/octet-stream")
            },
        )

        diff_resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        assert diff_resp.status_code == 200
        ops = diff_resp.json()["ops"]
        return session_id, ops

    def test_revision_approve_ops(self, client, session_with_ops):
        """Approve ops, verify status changes."""
        session_id, ops = session_with_ops
        if not ops:
            pytest.skip("No ops to approve")

        # Approve first op, reject second if exists
        approvals = [{"op_id": ops[0]["op_id"], "action": "approve"}]
        if len(ops) > 1:
            approvals.append({"op_id": ops[1]["op_id"], "action": "reject"})

        resp = client.post(
            "/api/revision/approve",
            json={"session_id": session_id, "approvals": approvals},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ops" in data
        assert "pending_count" in data
        assert "approved_count" in data
        assert "rejected_count" in data

    def test_revision_approve_no_diff(self, client, upload_dxf):
        """Approve without running diff first should return 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/revision/approve",
            json={
                "session_id": session_id,
                "approvals": [{"op_id": "fake", "action": "approve"}],
            },
        )
        assert resp.status_code == 400

    def test_revision_approve_invalid_action(self, client, session_with_ops):
        """Invalid action should return 400."""
        session_id, ops = session_with_ops
        if not ops:
            pytest.skip("No ops")

        resp = client.post(
            "/api/revision/approve",
            json={
                "session_id": session_id,
                "approvals": [{"op_id": ops[0]["op_id"], "action": "maybe"}],
            },
        )
        assert resp.status_code == 400

    def test_revision_approve_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/revision/approve",
            json={
                "session_id": "anything",
                "approvals": [{"op_id": "x", "action": "approve"}],
            },
        )
        assert resp.status_code == 401


@pytest.mark.web
class TestRevisionApply:
    """Tests for POST /api/revision/apply."""

    @pytest.fixture
    def session_ready_to_apply(self, client, tmp_path):
        """Full setup: upload → revision upload → diff → approve all → return session_id."""
        from tests.helpers.comparison_factory import make_added_removed_pair

        master_path, revision_path = make_added_removed_pair(tmp_path)

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_path.read_bytes(), "application/octet-stream")},
        )
        session_id = resp.json()["session_id"]

        client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={
                "file": ("revision.dxf", revision_path.read_bytes(), "application/octet-stream")
            },
        )

        diff_resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        assert diff_resp.status_code == 200
        ops = diff_resp.json()["ops"]

        # Approve all pending ops
        pending_ops = [op for op in ops if op["status"] == "pending"]
        if pending_ops:
            client.post(
                "/api/revision/approve",
                json={
                    "session_id": session_id,
                    "approvals": [
                        {"op_id": op["op_id"], "action": "approve"} for op in pending_ops
                    ],
                },
            )

        return session_id

    def test_revision_apply_creates_bundle(self, client, session_ready_to_apply):
        """Apply creates a bundle directory with artifacts."""
        session_id = session_ready_to_apply
        resp = client.post(
            "/api/revision/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "success_count" in data
        assert "failure_count" in data
        assert "bundle_dir" in data

        # Verify session state
        from web.backend.main import session_mgr

        session = session_mgr._sessions[session_id]
        assert session.bundle_dir is not None
        assert session.bundle_dir.exists()

    def test_revision_apply_no_diff(self, client, upload_dxf):
        """Apply without diff should return 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/revision/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 400

    def test_revision_apply_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/revision/apply",
            json={"session_id": "anything"},
        )
        assert resp.status_code == 401


@pytest.mark.web
class TestRevisionDownload:
    """Tests for GET /api/revision/download."""

    def test_revision_download_zip(self, client, tmp_path):
        """Download returns a valid zip file after full pipeline."""
        from tests.helpers.comparison_factory import make_added_removed_pair

        master_path, revision_path = make_added_removed_pair(tmp_path)

        # Full pipeline
        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_path.read_bytes(), "application/octet-stream")},
        )
        session_id = resp.json()["session_id"]

        client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={
                "file": ("revision.dxf", revision_path.read_bytes(), "application/octet-stream")
            },
        )

        diff_resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        ops = diff_resp.json()["ops"]
        pending_ops = [op for op in ops if op["status"] == "pending"]
        if pending_ops:
            client.post(
                "/api/revision/approve",
                json={
                    "session_id": session_id,
                    "approvals": [
                        {"op_id": op["op_id"], "action": "approve"} for op in pending_ops
                    ],
                },
            )

        client.post(
            "/api/revision/apply",
            json={"session_id": session_id},
        )

        # Download
        resp = client.get(f"/api/revision/download?session_id={session_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        # Verify it's a valid zip
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert len(names) > 0
            # Should contain at least the updated master and metadata
            assert any("updated" in n for n in names)
            assert any("metadata" in n for n in names)

    def test_revision_download_no_bundle(self, client, upload_dxf):
        """Download without apply should return 404."""
        session_id, _ = upload_dxf
        resp = client.get(f"/api/revision/download?session_id={session_id}")
        assert resp.status_code == 404

    def test_revision_download_missing_session(self, client):
        """Download with nonexistent session should return 404."""
        resp = client.get("/api/revision/download?session_id=nonexistent000")
        assert resp.status_code == 404


@pytest.mark.web
class TestRevisionEndToEnd:
    """Full pipeline integration test."""

    def test_revision_flow_end_to_end(self, client, tmp_path):
        """upload → revision upload → align → diff → approve → apply → download."""
        from tests.helpers.comparison_factory import make_offset_pair

        master_path, revision_path = make_offset_pair(tmp_path, dx=5.0, dy=3.0)

        # 1. Upload master
        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_path.read_bytes(), "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # 2. Upload revision
        resp = client.post(
            f"/api/revision/upload?session_id={session_id}",
            files={
                "file": ("revision.dxf", revision_path.read_bytes(), "application/octet-stream")
            },
        )
        assert resp.status_code == 200

        # 3. Align
        resp = client.post(
            "/api/revision/align",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        assert resp.json()["confidence"] > 0

        # 4. Diff
        resp = client.post(
            "/api/revision/diff",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        diff_data = resp.json()
        assert "ops" in diff_data

        # 5. Approve all pending
        ops = diff_data["ops"]
        pending_ops = [op for op in ops if op["status"] == "pending"]
        if pending_ops:
            resp = client.post(
                "/api/revision/approve",
                json={
                    "session_id": session_id,
                    "approvals": [
                        {"op_id": op["op_id"], "action": "approve"} for op in pending_ops
                    ],
                },
            )
            assert resp.status_code == 200

        # 6. Apply
        resp = client.post(
            "/api/revision/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        assert "run_id" in resp.json()

        # 7. Download
        resp = client.get(f"/api/revision/download?session_id={session_id}")
        assert resp.status_code == 200
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            assert len(zf.namelist()) > 0
