"""Tests for POST /api/compare endpoint.

Uses real pipeline components: ComparisonEngine, ezdxf. No mocks.
Factory helpers build deterministic DXF pairs for each scenario.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.web
class TestCompare:
    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def identical_revision_bytes(self, tmp_path):
        """Revision DXF identical to the base used by comparison_factory._build_base."""
        from tests.helpers.comparison_factory import _build_base

        revision_path = _build_base(tmp_path / "identical_revision.dxf")
        return revision_path.read_bytes()

    @pytest.fixture
    def master_and_identical_revision(self, tmp_path, client):
        """Upload a DXF built by _build_base, return (session_id, identical_revision_bytes)."""
        from tests.helpers.comparison_factory import _build_base

        master_bytes = _build_base(tmp_path / "master.dxf").read_bytes()
        revision_bytes = _build_base(tmp_path / "revision.dxf").read_bytes()

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        return session_id, revision_bytes

    @pytest.fixture
    def master_and_moved_revision(self, tmp_path, client):
        """Upload master; return (session_id, revision_bytes) where revision has a moved line."""
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master_path, revision_path = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)
        master_bytes = master_path.read_bytes()
        revision_bytes = revision_path.read_bytes()

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        return session_id, revision_bytes

    @pytest.fixture
    def master_and_added_removed_revision(self, tmp_path, client):
        """Upload master; return (session_id, revision_bytes) with added+removed entities."""
        from tests.helpers.comparison_factory import make_added_removed_pair

        master_path, revision_path = make_added_removed_pair(tmp_path)
        master_bytes = master_path.read_bytes()
        revision_bytes = revision_path.read_bytes()

        resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        return session_id, revision_bytes

    # ------------------------------------------------------------------
    # Happy-path structural tests
    # ------------------------------------------------------------------

    def test_compare_identical_files(self, client, master_and_identical_revision):
        session_id, revision_bytes = master_and_identical_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_changes"] == 0

    def test_compare_moved_entity(self, client, master_and_moved_revision):
        """Revision has one spatially-displaced line.

        The comparison engine classifies 'moved' only when entity handles match
        across both files (i.e. same DXF document saved twice). When master and
        revision are built as independent documents the displaced line appears as
        removed + added. Either way, total_changes must be non-zero.
        """
        session_id, revision_bytes = master_and_moved_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # At least one change detected (moved, or removed+added fallback)
        assert data["total_changes"] > 0
        summary = data["summary"]
        has_displacement = summary["moved"] > 0 or (summary["removed"] > 0 and summary["added"] > 0)
        assert has_displacement

    def test_compare_added_removed(self, client, master_and_added_removed_revision):
        session_id, revision_bytes = master_and_added_removed_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["added"] > 0
        assert data["summary"]["removed"] > 0

    def test_compare_returns_changelog(self, client, master_and_moved_revision):
        """changelog key must be a valid JSON string."""
        session_id, revision_bytes = master_and_moved_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "changelog" in data
        # Must be a non-empty JSON string that parses cleanly
        changelog = json.loads(data["changelog"])
        assert "entries" in changelog
        assert "summary" in changelog

    def test_compare_returns_render_available(self, client, master_and_identical_revision):
        """render_available must be a boolean."""
        session_id, revision_bytes = master_and_identical_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "render_available" in data
        assert isinstance(data["render_available"], bool)

    def test_compare_response_has_required_keys(self, client, master_and_identical_revision):
        """Verify the full response schema."""
        session_id, revision_bytes = master_and_identical_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "total_changes" in data
        assert "changelog" in data
        assert "render_available" in data

    def test_compare_summary_has_all_categories(self, client, master_and_identical_revision):
        """summary dict must contain all four change categories."""
        session_id, revision_bytes = master_and_identical_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        for key in ("added", "removed", "modified", "moved"):
            assert key in summary
            assert isinstance(summary[key], int)

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_compare_missing_session(self, client, sample_dxf_bytes):
        """Nonexistent session_id must return 404."""
        resp = client.post(
            "/api/compare?session_id=nonexistent000000",
            files={"file": ("revision.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 404

    def test_compare_wrong_user(self, client, sample_dxf_bytes):
        """Upload as user-A, then compare as user-B must return 404."""
        from web.backend.main import app, get_user

        # Upload as user-A
        async def user_a():
            return {"uid": "user-A", "email": "a@test.com"}

        app.dependency_overrides[get_user] = user_a
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200
        sid = upload_resp.json()["session_id"]

        # Compare as user-B
        async def user_b():
            return {"uid": "user-B", "email": "b@test.com"}

        app.dependency_overrides[get_user] = user_b
        resp = client.post(
            f"/api/compare?session_id={sid}",
            files={"file": ("revision.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 404

    def test_compare_non_dxf_file(self, client, upload_dxf):
        """Sending a .txt file must be rejected with 400."""
        session_id, _ = upload_dxf
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
        assert "dxf" in resp.json()["detail"].lower()

    def test_compare_corrupt_dxf(self, client, upload_dxf):
        """Garbage bytes with a .dxf extension must not return 200."""
        session_id, _ = upload_dxf
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={
                "file": (
                    "broken.dxf",
                    b"this is not a dxf file at all",
                    "application/octet-stream",
                )
            },
        )
        # Engine should raise on parse, so expect 400 or 500, never 200
        assert resp.status_code in (400, 500)

    def test_compare_no_master_loaded(self, client):
        """Compare against a session that has never had a file uploaded must return 400."""
        from web.backend.main import session_mgr

        session = session_mgr.create(user_id="test-user-123")
        # The session dir exists but original.dxf was never written — simulate by
        # leaving the session in its initial state (original_path points to a
        # non-existent file).
        resp = client.post(
            f"/api/compare?session_id={session.session_id}",
            files={"file": ("revision.dxf", b"", "application/octet-stream")},
        )
        assert resp.status_code in (400, 422)

    def test_compare_requires_auth(self, unauth_client, sample_dxf_bytes):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/compare?session_id=anything",
            files={"file": ("revision.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 401

    # ------------------------------------------------------------------
    # Complex scenarios
    # ------------------------------------------------------------------

    def test_compare_complex_pair_total_changes(self, tmp_path, client):
        """Complex pair: moved + removed + modified + added entities all counted."""
        from tests.helpers.comparison_factory import make_complex_pair

        master_path, revision_path = make_complex_pair(tmp_path)
        master_bytes = master_path.read_bytes()
        revision_bytes = revision_path.read_bytes()

        upload_resp = client.post(
            "/api/upload",
            files={"file": ("master.dxf", master_bytes, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Complex pair has multiple change types — total must be > 0
        assert data["total_changes"] > 0

    def test_compare_stores_result_in_session(self, client, master_and_moved_revision):
        """After a successful compare the session stores the result."""
        from web.backend.main import session_mgr

        session_id, revision_bytes = master_and_moved_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session = session_mgr._sessions[session_id]
        assert session.comparison_result is not None
        assert session.comparison_changelog is not None

    def test_compare_changelog_entries_match_changes(self, client, master_and_moved_revision):
        """Changelog entries must correspond to non-unchanged change categories."""
        session_id, revision_bytes = master_and_moved_revision
        resp = client.post(
            f"/api/compare?session_id={session_id}",
            files={"file": ("revision.dxf", revision_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        changelog = json.loads(resp.json()["changelog"])
        for entry in changelog["entries"]:
            assert entry["category"] in ("added", "removed", "modified", "moved")
            assert "entity_type" in entry
            assert "layer" in entry
            assert "description" in entry
