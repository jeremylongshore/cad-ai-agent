"""Tests for zone detection Pydantic models."""

from __future__ import annotations

from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult


class TestDetectedZone:
    """DetectedZone model tests."""

    def test_default_fields(self):
        zone = DetectedZone(
            boundary=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)],
            area=50.0,
            perimeter=34.14,
            centroid=Point2D(x=5, y=5),
        )
        assert zone.zone_id  # auto-generated
        assert zone.inferred_type is None
        assert zone.source_handles == []
        assert zone.confidence == 1.0

    def test_with_all_fields(self):
        zone = DetectedZone(
            zone_id="test-123",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=10),
                Point2D(x=0, y=10),
            ],
            area=100.0,
            perimeter=40.0,
            centroid=Point2D(x=5, y=5),
            inferred_type="room",
            source_handles=["A1", "A2"],
            confidence=0.9,
        )
        assert zone.zone_id == "test-123"
        assert zone.inferred_type == "room"
        assert len(zone.source_handles) == 2
        assert zone.confidence == 0.9

    def test_serialization_roundtrip(self):
        zone = DetectedZone(
            boundary=[Point2D(x=0, y=0), Point2D(x=5, y=0), Point2D(x=5, y=5)],
            area=12.5,
            perimeter=17.07,
            centroid=Point2D(x=3.33, y=1.67),
            inferred_type="closet",
        )
        data = zone.model_dump()
        restored = DetectedZone(**data)
        assert restored.area == zone.area
        assert restored.inferred_type == "closet"
        assert len(restored.boundary) == 3

    def test_unique_zone_ids(self):
        z1 = DetectedZone(
            boundary=[Point2D(x=0, y=0)],
            area=0,
            perimeter=0,
            centroid=Point2D(x=0, y=0),
        )
        z2 = DetectedZone(
            boundary=[Point2D(x=0, y=0)],
            area=0,
            perimeter=0,
            centroid=Point2D(x=0, y=0),
        )
        assert z1.zone_id != z2.zone_id


class TestZoneDetectionResult:
    """ZoneDetectionResult model tests."""

    def test_empty_defaults(self):
        result = ZoneDetectionResult()
        assert result.zones == []
        assert result.total_area == 0.0
        assert result.zone_count == 0
        assert result.confidence == 0.0
        assert result.method == "polyline_and_line_tracing"
        assert result.warnings == []

    def test_with_zones(self):
        zones = [
            DetectedZone(
                boundary=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)],
                area=50.0,
                perimeter=34.14,
                centroid=Point2D(x=5, y=5),
                inferred_type="room",
            ),
            DetectedZone(
                boundary=[Point2D(x=20, y=0), Point2D(x=30, y=0), Point2D(x=30, y=5)],
                area=25.0,
                perimeter=22.36,
                centroid=Point2D(x=25, y=2.5),
                inferred_type="closet",
            ),
        ]
        result = ZoneDetectionResult(
            zones=zones,
            total_area=75.0,
            zone_count=2,
            confidence=0.8,
        )
        assert result.zone_count == 2
        assert result.total_area == 75.0

    def test_serialization(self):
        result = ZoneDetectionResult(
            zone_count=1,
            total_area=100.0,
            confidence=0.5,
            warnings=["Low confidence detection"],
        )
        data = result.model_dump()
        assert data["warnings"] == ["Low confidence detection"]
        restored = ZoneDetectionResult(**data)
        assert restored.zone_count == 1
