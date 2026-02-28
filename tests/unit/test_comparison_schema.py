"""Tests for comparison_schema.py — Pydantic models."""

from __future__ import annotations

from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
    ComparisonResult,
    DiffOverlayLayers,
    EntityChange,
    GeometrySnapshot,
    MatchMethod,
    MatchResult,
    ScoredMatch,
)


class TestGeometrySnapshot:
    def test_centroid_single_point(self):
        snap = GeometrySnapshot(
            handle="A1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            points=[Point2D(x=10, y=20)],
        )
        assert snap.centroid.x == 10.0
        assert snap.centroid.y == 20.0

    def test_centroid_multiple_points(self):
        snap = GeometrySnapshot(
            handle="A2",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        assert snap.centroid.x == 5.0
        assert snap.centroid.y == 0.0

    def test_centroid_empty_points(self):
        snap = GeometrySnapshot(
            handle="A3",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[],
        )
        assert snap.centroid.x == 0.0
        assert snap.centroid.y == 0.0

    def test_centroid_four_corners(self):
        snap = GeometrySnapshot(
            handle="A4",
            entity_type=EntityType.LWPOLYLINE,
            layer="STRUCTURAL",
            points=[
                Point2D(x=0, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=10),
                Point2D(x=0, y=10),
            ],
        )
        assert snap.centroid.x == 5.0
        assert snap.centroid.y == 5.0

    def test_optional_fields_default_none(self):
        snap = GeometrySnapshot(
            handle="B1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0)],
        )
        assert snap.text_content is None
        assert snap.block_name is None
        assert snap.attributes == {}

    def test_text_content(self):
        snap = GeometrySnapshot(
            handle="B2",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            points=[Point2D(x=5, y=5)],
            text_content="Hello",
        )
        assert snap.text_content == "Hello"

    def test_block_name(self):
        snap = GeometrySnapshot(
            handle="B3",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            points=[Point2D(x=1, y=1)],
            block_name="COLUMN_MARK",
        )
        assert snap.block_name == "COLUMN_MARK"

    def test_attributes(self):
        snap = GeometrySnapshot(
            handle="B4",
            entity_type=EntityType.CIRCLE,
            layer="STRUCTURAL",
            points=[Point2D(x=50, y=50)],
            attributes={"radius": 10.0},
        )
        assert snap.attributes["radius"] == 10.0

    def test_serialization_round_trip(self):
        snap = GeometrySnapshot(
            handle="C1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=5)],
            text_content=None,
            block_name=None,
            attributes={"custom": "value"},
        )
        data = snap.model_dump()
        restored = GeometrySnapshot(**data)
        assert restored.handle == "C1"
        assert restored.centroid.x == 5.0
        assert restored.centroid.y == 2.5


class TestComparisonConfig:
    def test_defaults(self):
        config = ComparisonConfig()
        assert config.tolerance == 0.25
        assert config.move_threshold == 0.25
        assert config.ignored_layers == []
        assert config.focus_entity_types is None

    def test_custom_values(self):
        config = ComparisonConfig(
            tolerance=0.5,
            move_threshold=1.0,
            ignored_layers=["TEMP"],
            focus_entity_types=[EntityType.LINE, EntityType.TEXT],
        )
        assert config.tolerance == 0.5
        assert config.focus_entity_types is not None
        assert len(config.focus_entity_types) == 2


class TestChangeCategory:
    def test_values(self):
        assert ChangeCategory.ADDED == "added"
        assert ChangeCategory.REMOVED == "removed"
        assert ChangeCategory.MODIFIED == "modified"
        assert ChangeCategory.MOVED == "moved"
        assert ChangeCategory.UNCHANGED == "unchanged"

    def test_is_strenum(self):
        assert isinstance(ChangeCategory.ADDED, str)


class TestEntityChange:
    def test_added(self):
        snap = GeometrySnapshot(
            handle="X1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0)],
        )
        change = EntityChange(
            category=ChangeCategory.ADDED,
            revision_snapshot=snap,
        )
        assert change.category == ChangeCategory.ADDED
        assert change.master_snapshot is None
        assert change.revision_snapshot is not None

    def test_removed(self):
        snap = GeometrySnapshot(
            handle="X2",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            points=[Point2D(x=5, y=5)],
        )
        change = EntityChange(
            category=ChangeCategory.REMOVED,
            master_snapshot=snap,
        )
        assert change.revision_snapshot is None

    def test_moved_with_displacement(self):
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=GeometrySnapshot(
                handle="M1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0)],
            ),
            revision_snapshot=GeometrySnapshot(
                handle="R1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=5, y=5)],
            ),
            displacement=Point2D(x=5, y=5),
        )
        assert change.displacement is not None
        assert change.displacement.x == 5.0

    def test_modified_with_modifications(self):
        change = EntityChange(
            category=ChangeCategory.MODIFIED,
            master_snapshot=GeometrySnapshot(
                handle="M2",
                entity_type=EntityType.TEXT,
                layer="N",
                points=[Point2D(x=10, y=10)],
                text_content="Old",
            ),
            revision_snapshot=GeometrySnapshot(
                handle="R2",
                entity_type=EntityType.TEXT,
                layer="N",
                points=[Point2D(x=10, y=10)],
                text_content="New",
            ),
            modifications={"text_content": {"from": "Old", "to": "New"}},
        )
        assert change.modifications is not None
        assert "text_content" in change.modifications


class TestMatchResult:
    def test_empty(self):
        mr = MatchResult()
        assert mr.pairs == []
        assert mr.master_only == []
        assert mr.revision_only == []

    def test_with_pairs(self):
        s1 = GeometrySnapshot(
            handle="A",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0, y=0)],
        )
        s2 = GeometrySnapshot(
            handle="B",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0, y=0)],
        )
        mr = MatchResult(
            pairs=[
                ScoredMatch(
                    master=s1,
                    revision=s2,
                    confidence=1.0,
                    method=MatchMethod.fingerprint,
                )
            ]
        )
        assert len(mr.pairs) == 1


class TestComparisonResult:
    def test_default_summary(self):
        result = ComparisonResult()
        assert result.summary["added"] == 0
        assert result.total_changes == 0

    def test_total_changes(self):
        result = ComparisonResult(
            summary={"added": 3, "removed": 1, "modified": 2, "moved": 1, "unchanged": 10}
        )
        assert result.total_changes == 7


class TestDiffOverlayLayers:
    def test_layer_names(self):
        assert DiffOverlayLayers.ADDED[0] == "AI_ADDED"
        assert DiffOverlayLayers.REMOVED[0] == "AI_REMOVED"
        assert DiffOverlayLayers.MODIFIED[0] == "AI_MODIFIED"
        assert DiffOverlayLayers.MOVED[0] == "AI_MOVED"

    def test_color_codes(self):
        assert DiffOverlayLayers.ADDED[1] == 3  # green
        assert DiffOverlayLayers.REMOVED[1] == 1  # red
        assert DiffOverlayLayers.MODIFIED[1] == 2  # yellow
        assert DiffOverlayLayers.MOVED[1] == 4  # cyan

    def test_all_list(self):
        assert len(DiffOverlayLayers.ALL) == 4
