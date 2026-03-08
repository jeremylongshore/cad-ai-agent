"""Tests for API v1 — stateless drawing intelligence endpoints.

These endpoints accept DXF file uploads directly (no session) and
return structured JSON. Designed for agent/CLI/CI consumption.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers.dxf_factory import (
    create_empty_dxf,
    create_empty_layers_drawing,
    create_structural_drawing,
)


@pytest.fixture()
def client():
    """Create a test client with dev mode (no auth)."""
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


def _upload(client: TestClient, path: str, dxf_path: Path):
    """Helper to POST a DXF file to a v1 endpoint."""
    with open(dxf_path, "rb") as f:
        return client.post(path, files={"file": ("test.dxf", f)})


# ===================================================================
# POST /api/v1/analyze
# ===================================================================


class TestV1Analyze:
    """Test the /api/v1/analyze endpoint."""

    def test_analyze_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/analyze", dxf)
        assert resp.status_code == 200
        data = resp.json()

        assert "entity_count" in data
        assert data["entity_count"] > 0
        assert "layer_count" in data
        assert data["layer_count"] > 0
        assert "layers" in data
        assert isinstance(data["layers"], list)
        assert "entity_types" in data
        assert isinstance(data["entity_types"], dict)

    def test_analyze_returns_layer_breakdown(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/analyze", dxf)
        data = resp.json()

        layer_names = {lr["name"] for lr in data["layers"]}
        assert "STRUCTURAL" in layer_names
        assert "NOTES" in layer_names

        for layer in data["layers"]:
            assert "entity_count" in layer
            assert "name" in layer

    def test_analyze_returns_type_distribution(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/analyze", dxf)
        data = resp.json()

        assert "LINE" in data["entity_types"] or "TEXT" in data["entity_types"]

    def test_analyze_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/analyze", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_count"] == 0

    def test_analyze_rejects_non_dxf(self, client, tmp_path):
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("not a dxf")
        with open(txt_path, "rb") as f:
            resp = client.post(
                "/api/v1/analyze",
                files={"file": ("test.txt", f)},
            )
        assert resp.status_code == 400


# ===================================================================
# POST /api/v1/health
# ===================================================================


class TestV1Health:
    """Test the /api/v1/health endpoint.

    Health checker may not be available on all branches (EPIC-CAD-19).
    Tests accept either 200 (available) or 501 (not yet merged).
    """

    @staticmethod
    def _health_available():
        try:
            import cad_dxf_agent.core.health_checker  # noqa: F401

            return True
        except ImportError:
            return False

    def test_health_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/health", dxf)
        if not self._health_available():
            assert resp.status_code == 501
            return

        assert resp.status_code == 200
        data = resp.json()

        assert "score" in data
        assert 0 <= data["score"] <= 100
        assert "summary" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)
        assert "checks_run" in data
        assert len(data["checks_run"]) > 0

    def test_health_issue_structure(self, client, tmp_path):
        if not self._health_available():
            pytest.skip("health_checker not available")
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/health", dxf)
        data = resp.json()

        for issue in data["issues"]:
            assert "severity" in issue
            assert "category" in issue
            assert "title" in issue
            assert "description" in issue
            assert issue["severity"] in ("critical", "warning", "info")

    def test_health_severity_counts(self, client, tmp_path):
        if not self._health_available():
            pytest.skip("health_checker not available")
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/health", dxf)
        data = resp.json()

        assert "critical_count" in data
        assert "warning_count" in data
        assert "info_count" in data
        assert isinstance(data["critical_count"], int)

    def test_health_empty_drawing(self, client, tmp_path):
        if not self._health_available():
            pytest.skip("health_checker not available")
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/health", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 0  # empty drawing = 0 score

    def test_health_drawing_with_orphan_layers(self, client, tmp_path):
        """Drawing with empty layers should flag orphan layer issues."""
        if not self._health_available():
            pytest.skip("health_checker not available")
        dxf = create_empty_layers_drawing(tmp_path)
        resp = _upload(client, "/api/v1/health", dxf)
        data = resp.json()

        layer_issues = [i for i in data["issues"] if i["category"] == "layer"]
        assert len(layer_issues) > 0


# ===================================================================
# POST /api/v1/zones
# ===================================================================


class TestV1Zones:
    """Test the /api/v1/zones endpoint."""

    def test_zones_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/zones", dxf)
        assert resp.status_code == 200
        data = resp.json()

        assert "zone_count" in data
        assert isinstance(data["zone_count"], int)
        assert "total_area" in data
        assert "zones" in data
        assert isinstance(data["zones"], list)

    def test_zones_structure(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/zones", dxf)
        data = resp.json()

        for zone in data["zones"]:
            assert "area" in zone
            assert "centroid" in zone
            assert "x" in zone["centroid"]
            assert "y" in zone["centroid"]

    def test_zones_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/zones", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert data["zone_count"] == 0
        assert data["zones"] == []


# ===================================================================
# POST /api/v1/entities
# ===================================================================


class TestV1Entities:
    """Test the /api/v1/entities endpoint."""

    def test_entities_unfiltered(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities",
                files={"file": ("test.dxf", f)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "entities" in data
        assert data["total"] > 0

    def test_entities_filter_by_layer(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities?layer=STRUCTURAL",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        for e in data["entities"]:
            assert e["layer"] == "STRUCTURAL"

    def test_entities_filter_by_type(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities?entity_type=TEXT",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        for e in data["entities"]:
            assert e["type"] == "TEXT"

    def test_entities_filter_by_text(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities?text_contains=FOOTING",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        assert data["total"] > 0
        for e in data["entities"]:
            assert "text" in e

    def test_entities_with_limit(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities?limit=5",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        assert data["returned"] <= 5

    def test_entities_entity_structure(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        for e in data["entities"]:
            assert "handle" in e
            assert "type" in e
            assert "layer" in e

    def test_entities_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/entities",
                files={"file": ("test.dxf", f)},
            )
        data = resp.json()
        assert data["total"] == 0
        assert data["entities"] == []


# ===================================================================
# POST /api/v1/compliance
# ===================================================================


class TestV1Compliance:
    """Test the /api/v1/compliance endpoint."""

    def test_compliance_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/compliance", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "passed" in data
        assert "score" in data
        assert "findings" in data
        assert "checks_run" in data

    def test_compliance_default_profile_is_ibc(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/compliance", dxf)
        assert resp.json()["profile"] == "ibc-2021"

    def test_compliance_ada_profile(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/compliance?profile=ada",
                files={"file": ("test.dxf", f)},
            )
        assert resp.status_code == 200
        assert resp.json()["profile"] == "ada"

    def test_compliance_unknown_profile(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        with open(dxf, "rb") as f:
            resp = client.post(
                "/api/v1/compliance?profile=nonexistent",
                files={"file": ("test.dxf", f)},
            )
        assert resp.status_code == 422

    def test_compliance_score_range(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/compliance", dxf)
        score = resp.json()["score"]
        assert 0 <= score <= 100

    def test_compliance_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/compliance", dxf)
        assert resp.status_code == 200


# ===================================================================
# POST /api/v1/takeoff
# ===================================================================


class TestV1Takeoff:
    """Test the /api/v1/takeoff endpoint."""

    def test_takeoff_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/takeoff", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_takeoff_has_methodology(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/takeoff", dxf)
        data = resp.json()
        assert "methodology" in data

    def test_takeoff_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/takeoff", dxf)
        assert resp.status_code == 200


# ===================================================================
# POST /api/v1/summary
# ===================================================================


class TestV1Summary:
    """Test the /api/v1/summary endpoint."""

    def test_summary_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/summary", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert "headline" in data
        assert "drawing_type" in data
        assert "entity_count" in data
        assert "layer_count" in data

    def test_summary_has_description(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/summary", dxf)
        data = resp.json()
        assert "plain_description" in data
        assert len(data["plain_description"]) > 0

    def test_summary_has_key_features(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/summary", dxf)
        data = resp.json()
        assert "key_features" in data
        assert isinstance(data["key_features"], list)

    def test_summary_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/summary", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_count"] == 0


# ===================================================================
# POST /api/v1/rfi
# ===================================================================


class TestV1RFI:
    """Test the /api/v1/rfi endpoint."""

    def test_rfi_structural(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/rfi", dxf)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_items" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_rfi_has_severity_counts(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/rfi", dxf)
        data = resp.json()
        assert "critical_count" in data
        assert "major_count" in data
        assert "minor_count" in data

    def test_rfi_item_structure(self, client, tmp_path):
        dxf = create_structural_drawing(tmp_path)
        resp = _upload(client, "/api/v1/rfi", dxf)
        data = resp.json()
        for item in data["items"]:
            assert "rfi_id" in item
            assert "category" in item
            assert "severity" in item
            assert "question" in item

    def test_rfi_empty_drawing(self, client, tmp_path):
        dxf = create_empty_dxf(tmp_path)
        resp = _upload(client, "/api/v1/rfi", dxf)
        assert resp.status_code == 200
