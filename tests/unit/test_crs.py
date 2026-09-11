"""Tests for drawing CRS resolution and coordinate transforms."""

from __future__ import annotations

import ezdxf
import pytest
from ezdxf.math import Matrix44
from pyproj import CRS

from cad_dxf_agent.core.crs import (
    CRSResolutionError,
    MissingCRSError,
    drawing_to_wgs84,
    resolve_drawing_crs,
    validate_crs_units,
    wgs84_to_drawing,
)
from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.models.cad_schema import CRSSource, DrawingCRS, DrawingUnit, Point2D


class _FakeGeoData:
    def get_crs_transformation(self):
        return Matrix44.translate(500_000, 3_600_000, 0), 26916


class _FakeModelspace:
    def __init__(self, geodata):
        self._geodata = geodata

    def get_geodata(self):
        return self._geodata


class _FakeDocument:
    def __init__(self, geodata=None):
        self._modelspace = _FakeModelspace(geodata)

    def modelspace(self):
        return self._modelspace


def test_missing_crs_is_explicit(tmp_path):
    assert resolve_drawing_crs(_FakeDocument(), tmp_path / "drawing.dxf") is None
    with pytest.raises(MissingCRSError, match="Drawing has no CRS"):
        drawing_to_wgs84(Point2D(x=1, y=2), None)


def test_caller_crs_has_precedence_over_prj(tmp_path):
    path = tmp_path / "drawing.dxf"
    path.with_suffix(".prj").write_text("not a valid CRS", encoding="utf-8")

    resolved = resolve_drawing_crs(_FakeDocument(), path, "EPSG:26916")

    assert resolved is not None
    assert resolved.definition == "EPSG:26916"
    assert resolved.source is CRSSource.CALLER


def test_prj_sidecar_is_resolved(tmp_path):
    path = tmp_path / "drawing.dxf"
    path.with_suffix(".prj").write_text(CRS.from_epsg(32616).to_wkt(), encoding="utf-8")

    resolved = resolve_drawing_crs(_FakeDocument(), path)

    assert resolved is not None
    assert resolved.definition == "EPSG:32616"
    assert resolved.source is CRSSource.PRJ


def test_invalid_present_crs_fails_closed(tmp_path):
    with pytest.raises(CRSResolutionError, match="Invalid caller CRS"):
        resolve_drawing_crs(_FakeDocument(), tmp_path / "drawing.dxf", "EPSG:not-real")


def test_dxf_geodata_carries_local_grid_transform(tmp_path):
    resolved = resolve_drawing_crs(
        _FakeDocument(_FakeGeoData()),
        tmp_path / "drawing.dxf",
    )

    assert resolved is not None
    assert resolved.source is CRSSource.DXF_GEODATA
    assert resolved.definition == "EPSG:26916"
    assert resolved.drawing_to_crs_matrix is not None

    geographic = drawing_to_wgs84(Point2D(x=0, y=0), resolved)
    direct = drawing_to_wgs84(
        Point2D(x=500_000, y=3_600_000),
        DrawingCRS(definition="EPSG:26916", name="NAD83 / UTM zone 16N", source=CRSSource.CALLER),
    )
    assert geographic.x == pytest.approx(direct.x)
    assert geographic.y == pytest.approx(direct.y)


def test_wgs84_round_trip_preserves_xy_and_z():
    crs = DrawingCRS(
        definition="EPSG:26916",
        name="NAD83 / UTM zone 16N",
        source=CRSSource.CALLER,
    )
    drawing = Point2D(x=500_000, y=3_600_000, z=125.5)

    round_trip = wgs84_to_drawing(drawing_to_wgs84(drawing, crs), crs)

    assert round_trip.x == pytest.approx(drawing.x, abs=1e-6)
    assert round_trip.y == pytest.approx(drawing.y, abs=1e-6)
    assert round_trip.z == pytest.approx(drawing.z)


def test_projected_crs_rejects_conflicting_dxf_units():
    crs = DrawingCRS(
        definition="EPSG:26916",
        name="NAD83 / UTM zone 16N",
        source=CRSSource.CALLER,
    )

    validate_crs_units(crs, DrawingUnit.METERS)
    with pytest.raises(CRSResolutionError, match="conflicts"):
        validate_crs_units(crs, DrawingUnit.FEET)


def test_load_dxf_accepts_caller_crs(tmp_path):
    doc = ezdxf.new(dxfversion="R2018")
    doc.modelspace().add_line((0, 0), (1, 1))
    path = tmp_path / "drawing.dxf"
    doc.saveas(path)

    context = load_dxf(path, crs="EPSG:26916")

    assert context.crs is not None
    assert context.crs.definition == "EPSG:26916"
    assert context.metadata["crs_source"] == "caller"
