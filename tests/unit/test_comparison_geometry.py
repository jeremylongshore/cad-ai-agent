"""Tests for comparison/geometry.py — geometry extraction from DXF."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.geometry import (
    apply_profile,
    check_profile_warnings,
    detect_titleblock_region,
    extract_snapshots,
)
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.comparison_schema import BBoxRegion, ComparisonConfig, ComparisonProfile
from tests.helpers.comparison_factory import (
    make_circle_pair,
    make_complex_pair,
    make_geometry_snapshot,
    make_identical_pair,
)


class TestExtractSnapshots:
    def test_basic_extraction(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        assert len(snaps) > 0

    def test_line_has_two_points(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        lines = [s for s in snaps if s.entity_type == EntityType.LINE]
        assert len(lines) >= 1
        for line in lines:
            assert len(line.points) == 2

    def test_text_has_content(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        texts = [s for s in snaps if s.entity_type == EntityType.TEXT]
        assert len(texts) >= 1
        for text in texts:
            assert text.text_content is not None
            assert len(text.points) == 1

    def test_lwpolyline_has_all_vertices(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        polys = [s for s in snaps if s.entity_type == EntityType.LWPOLYLINE]
        assert len(polys) >= 1
        for poly in polys:
            assert len(poly.points) >= 2

    def test_circle_has_radius(self, tmp_path):
        master, _ = make_circle_pair(tmp_path)
        snaps = extract_snapshots(master)
        circles = [s for s in snaps if s.entity_type == EntityType.CIRCLE]
        assert len(circles) == 1
        assert circles[0].attributes["radius"] == 10.0
        assert circles[0].points[0].x == 50.0
        assert circles[0].points[0].y == 50.0

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_snapshots(tmp_path / "nonexistent.dxf")

    def test_ignored_layers(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        config = ComparisonConfig(ignored_layers=["NOTES"])
        snaps = extract_snapshots(master, config)
        for snap in snaps:
            assert snap.layer != "NOTES"

    def test_focus_entity_types(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        config = ComparisonConfig(focus_entity_types=[EntityType.LINE])
        snaps = extract_snapshots(master, config)
        for snap in snaps:
            assert snap.entity_type == EntityType.LINE

    def test_centroid_computed(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            # Centroid should be finite
            assert snap.centroid.x != float("inf")
            assert snap.centroid.y != float("inf")

    def test_handles_are_strings(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            assert isinstance(snap.handle, str)
            assert len(snap.handle) > 0

    def test_complex_drawing(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        snaps = extract_snapshots(master)
        types = {s.entity_type for s in snaps}
        assert EntityType.LINE in types
        assert EntityType.TEXT in types
        assert EntityType.LWPOLYLINE in types


class TestExtractFromMixedDrawing:
    """Test extraction from a drawing with multiple entity types."""

    def test_all_entities_have_points(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            assert len(snap.points) > 0, f"{snap.entity_type} has no points"


# --- Helper to build test snapshots quickly ---


def _snaps() -> list:
    """Build a mix of snapshots for apply_profile tests."""
    mk = make_geometry_snapshot
    return [
        mk(handle="L1", entity_type=EntityType.LINE, layer="STRUCTURAL", points=[(0, 0), (10, 0)]),
        mk(handle="L2", entity_type=EntityType.LINE, layer="GRID", points=[(0, 0), (0, 100)]),
        mk(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            points=[(50, 50)],
            text_content="Note A",
        ),
        mk(
            handle="T2",
            entity_type=EntityType.TEXT,
            layer="TITLEBLOCK",
            points=[(5, 5)],
            text_content="Title",
        ),
        mk(
            handle="P1",
            entity_type=EntityType.LWPOLYLINE,
            layer="STRUCTURAL",
            points=[(20, 20), (30, 20), (30, 30)],
        ),
        mk(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            points=[(200, 200)],
            block_name="COL",
        ),
    ]


class TestApplyProfile:
    """Pure unit tests for apply_profile — no DXF, just GeometrySnapshot lists."""

    def test_no_filters(self):
        snaps = _snaps()
        profile = ComparisonProfile()
        result = apply_profile(snaps, profile)
        assert len(result) == len(snaps)

    def test_include_entity_types(self):
        snaps = _snaps()
        profile = ComparisonProfile(include_entity_types=[EntityType.LINE])
        result = apply_profile(snaps, profile)
        assert all(s.entity_type == EntityType.LINE for s in result)
        assert len(result) == 2

    def test_include_layers_regex(self):
        snaps = _snaps()
        profile = ComparisonProfile(include_layers=[r"^STRUCT"])
        result = apply_profile(snaps, profile)
        assert all(s.layer == "STRUCTURAL" for s in result)
        assert len(result) == 3  # L1, P1, I1

    def test_exclude_layers_regex(self):
        snaps = _snaps()
        profile = ComparisonProfile(exclude_layers=[r"(?i)^notes$"])
        result = apply_profile(snaps, profile)
        assert all(s.layer != "NOTES" for s in result)
        assert len(result) == 5

    def test_include_then_exclude(self):
        """Include STRUCTURAL and NOTES, then exclude NOTES — only STRUCTURAL remains."""
        snaps = _snaps()
        profile = ComparisonProfile(
            include_layers=[r"^STRUCTURAL$", r"^NOTES$"],
            exclude_layers=[r"^NOTES$"],
        )
        result = apply_profile(snaps, profile)
        assert all(s.layer == "STRUCTURAL" for s in result)
        assert len(result) == 3

    def test_exclude_regions(self):
        snaps = _snaps()
        # Exclude region covering (0,0)-(15,15) — should drop L1, T2
        profile = ComparisonProfile(
            exclude_regions=[BBoxRegion(min_x=0, min_y=0, max_x=15, max_y=15)],
        )
        result = apply_profile(snaps, profile)
        excluded_handles = {s.handle for s in snaps} - {s.handle for s in result}
        # L1 centroid=(5,0), T2 centroid=(5,5) — both inside
        assert "L1" in excluded_handles
        assert "T2" in excluded_handles

    def test_exclude_regions_edge(self):
        """Boundary is inclusive — entity exactly on edge is excluded."""
        snap = make_geometry_snapshot(
            handle="EDGE",
            entity_type=EntityType.LINE,
            layer="X",
            points=[(10, 10), (10, 10)],
        )
        profile = ComparisonProfile(
            exclude_regions=[BBoxRegion(min_x=10, min_y=10, max_x=20, max_y=20)],
        )
        result = apply_profile([snap], profile)
        assert len(result) == 0


class TestProfileViaExtraction:
    """Integration: profile on ComparisonConfig filters during extract_snapshots."""

    def test_profile_excludes_notes_layer(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        config = ComparisonConfig(
            profile=ComparisonProfile(exclude_layers=[r"(?i)^notes$"]),
        )
        snaps = extract_snapshots(master, config)
        assert all(s.layer.upper() != "NOTES" for s in snaps)

    def test_structural_preset_filters(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        config = ComparisonConfig(profile=ComparisonProfile.structural())
        snaps = extract_snapshots(master, config)
        # structural() excludes NOTES and only includes structural types
        allowed_types = {
            EntityType.LINE,
            EntityType.LWPOLYLINE,
            EntityType.CIRCLE,
            EntityType.ARC,
            EntityType.INSERT,
        }
        for s in snaps:
            assert s.entity_type in allowed_types, f"{s.entity_type} should be filtered"
            assert not s.layer.upper().startswith("NOTE"), f"Layer {s.layer} should be excluded"


# --- Titleblock auto-detect tests ---


class TestDetectTitleblockRegion:
    def test_no_titleblock_layers_returns_none(self):
        snaps = [
            make_geometry_snapshot(handle="L1", layer="STRUCTURAL", points=[(0, 0), (10, 0)]),
        ]
        assert detect_titleblock_region(snaps) is None

    def test_title_layer_detected(self):
        snaps = [
            make_geometry_snapshot(handle="T1", layer="TITLE", points=[(100, 0), (200, 10)]),
            make_geometry_snapshot(handle="L1", layer="STRUCTURAL", points=[(0, 0), (10, 0)]),
        ]
        region = detect_titleblock_region(snaps)
        assert region is not None
        assert region.min_x == 95.0  # 100 - 5 padding
        assert region.max_x == 205.0  # 200 + 5 padding

    def test_titleblock_layer_detected(self):
        snaps = [
            make_geometry_snapshot(handle="TB1", layer="TITLEBLOCK", points=[(50, 50), (150, 80)]),
        ]
        region = detect_titleblock_region(snaps)
        assert region is not None
        assert region.min_x == 45.0
        assert region.max_y == 85.0

    def test_seal_and_revision_layers_detected(self):
        snaps = [
            make_geometry_snapshot(handle="S1", layer="SEAL", points=[(10, 10)]),
            make_geometry_snapshot(handle="R1", layer="REVISION_TABLE", points=[(20, 20)]),
        ]
        region = detect_titleblock_region(snaps)
        assert region is not None
        assert region.contains(10, 10)
        assert region.contains(20, 20)

    def test_border_layer_not_detected(self):
        """BORDER excluded from detection — can cover entire sheet."""
        snaps = [
            make_geometry_snapshot(
                handle="B1",
                entity_type=EntityType.LWPOLYLINE,
                layer="BORDER",
                points=[(0, 0), (100, 0), (100, 50), (0, 50)],
            ),
        ]
        assert detect_titleblock_region(snaps) is None

    def test_custom_padding(self):
        snaps = [
            make_geometry_snapshot(handle="T1", layer="TITLE", points=[(10, 10), (20, 20)]),
        ]
        region = detect_titleblock_region(snaps, padding=0)
        assert region is not None
        assert region.min_x == 10.0
        assert region.max_x == 20.0

    def test_empty_snapshots_returns_none(self):
        assert detect_titleblock_region([]) is None

    def test_case_insensitive_match(self):
        snaps = [
            make_geometry_snapshot(handle="T1", layer="Title_Block", points=[(5, 5)]),
        ]
        region = detect_titleblock_region(snaps)
        assert region is not None


# --- Profile warning tests ---


class TestCheckProfileWarnings:
    def test_under_threshold_no_warning(self):
        """<80% excluded → no warning."""
        mk = make_geometry_snapshot
        remaining = [mk(handle=f"L{i}", layer="A", points=[(i, 0)]) for i in range(5)]
        profile = ComparisonProfile(name="test")
        warnings = check_profile_warnings(10, remaining, profile)
        assert len(warnings) == 0

    def test_over_threshold_warns(self):
        """90% excluded → warning with percentage."""
        mk = make_geometry_snapshot
        remaining = [mk(handle="L1", layer="A", points=[(0, 0)])]
        profile = ComparisonProfile(name="strict")
        warnings = check_profile_warnings(10, remaining, profile)
        assert len(warnings) == 1
        assert "90%" in warnings[0]
        assert "strict" in warnings[0]

    def test_all_excluded_specific_warning(self):
        """All excluded → 'no geometry remains' warning."""
        profile = ComparisonProfile(name="nuke")
        warnings = check_profile_warnings(10, [], profile)
        assert len(warnings) == 1
        assert "no geometry remains" in warnings[0]

    def test_structural_missing_warning(self):
        """Only TEXT remaining with include_entity_types → structural warning."""
        mk = make_geometry_snapshot
        remaining = [
            mk(handle="T1", entity_type=EntityType.TEXT, layer="A", points=[(0, 0)]),
        ]
        profile = ComparisonProfile(
            name="filtered",
            include_entity_types=[EntityType.TEXT, EntityType.LINE],
        )
        warnings = check_profile_warnings(5, remaining, profile)
        assert any("LINE/LWPOLYLINE" in w for w in warnings)

    def test_line_present_no_structural_warning(self):
        """LINE remaining → no structural warning."""
        mk = make_geometry_snapshot
        remaining = [
            mk(handle="L1", entity_type=EntityType.LINE, layer="A", points=[(0, 0), (1, 1)]),
        ]
        profile = ComparisonProfile(
            name="ok",
            include_entity_types=[EntityType.LINE],
        )
        warnings = check_profile_warnings(5, remaining, profile)
        assert not any("LINE/LWPOLYLINE" in w for w in warnings)

    def test_zero_input_no_crash(self):
        """Zero before_count → no crash, no warnings."""
        profile = ComparisonProfile(name="empty")
        warnings = check_profile_warnings(0, [], profile)
        assert warnings == []

    def test_source_prefix_in_warnings(self):
        """source param prepends label to warning messages."""
        profile = ComparisonProfile(name="strict")
        warnings = check_profile_warnings(10, [], profile, source="master")
        assert len(warnings) == 1
        assert warnings[0].startswith("master: ")


# --- Xref and dynamic block detection tests ---


class TestXrefDetection:
    def test_xref_warning_emitted(self, tmp_path):
        """Files with xref blocks produce a warning."""
        from tests.helpers.comparison_factory import make_xref_pair

        master, _revision = make_xref_pair(tmp_path)
        warnings: list[str] = []
        extract_snapshots(master, _profile_warnings=warnings, _source="master")

        assert any("external reference" in w.lower() for w in warnings)

    def test_xref_entities_still_extracted(self, tmp_path):
        """Xref INSERTs are not excluded — they're still in the snapshot list."""
        from tests.helpers.comparison_factory import make_xref_pair

        master, _revision = make_xref_pair(tmp_path)
        snaps = extract_snapshots(master)

        # Should include the xref INSERT along with structural entities
        insert_snaps = [s for s in snaps if s.entity_type.value == "INSERT"]
        assert len(insert_snaps) > 0

    def test_no_warning_without_xrefs(self, tmp_path):
        """Normal files produce no xref warnings."""
        from tests.helpers.comparison_factory import make_identical_pair

        master, _revision = make_identical_pair(tmp_path)
        warnings: list[str] = []
        extract_snapshots(master, _profile_warnings=warnings, _source="master")

        assert not any("external reference" in w.lower() for w in warnings)

    def test_xref_warning_includes_source_prefix(self, tmp_path):
        """Xref warning respects the _source label."""
        from tests.helpers.comparison_factory import make_xref_pair

        master, _revision = make_xref_pair(tmp_path)
        warnings: list[str] = []
        extract_snapshots(master, _profile_warnings=warnings, _source="master")

        xref_warnings = [w for w in warnings if "external reference" in w.lower()]
        assert len(xref_warnings) == 1
        assert xref_warnings[0].startswith("master: ")

    def test_xref_warning_names_the_block(self, tmp_path):
        """Xref warning includes the block name(s) involved."""
        from tests.helpers.comparison_factory import make_xref_pair

        master, _revision = make_xref_pair(tmp_path)
        warnings: list[str] = []
        extract_snapshots(master, _profile_warnings=warnings)

        xref_warnings = [w for w in warnings if "external reference" in w.lower()]
        assert len(xref_warnings) == 1
        assert "GRID_REF" in xref_warnings[0]


# --- Entity-type extraction tests (_extract_one branches) ---


class TestExtractOneEntityTypes:
    """Test _extract_one() for entity types not covered by the base tests."""

    def test_arc_extraction(self, tmp_path):
        """ARC entities are extracted with radius and angle attributes."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        msp.add_arc((50, 50), radius=10, start_angle=0, end_angle=180, dxfattribs={"layer": "L"})
        path = tmp_path / "arc.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        arcs = [s for s in snaps if s.entity_type == EntityType.ARC]
        assert len(arcs) == 1
        assert arcs[0].attributes["radius"] == 10
        assert arcs[0].attributes["start_angle"] == 0
        assert arcs[0].attributes["end_angle"] == 180
        assert len(arcs[0].points) == 1  # centre point

    def test_ellipse_extraction(self, tmp_path):
        """ELLIPSE entities are extracted with ratio and major_axis attributes."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        msp.add_ellipse(
            center=(30, 30), major_axis=(10, 0, 0), ratio=0.5, dxfattribs={"layer": "L"}
        )
        path = tmp_path / "ellipse.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        ellipses = [s for s in snaps if s.entity_type == EntityType.ELLIPSE]
        assert len(ellipses) == 1
        assert ellipses[0].attributes["ratio"] == pytest.approx(0.5)
        assert "major_axis" in ellipses[0].attributes
        assert len(ellipses[0].points) == 1  # centre point

    def test_spline_extraction(self, tmp_path):
        """SPLINE entities are extracted with control points."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        # add_spline with fit_points does not populate control_points; set them directly
        spline = msp.add_spline(dxfattribs={"layer": "L"})
        spline.control_points = [(0, 0, 0), (5, 10, 0), (10, 0, 0)]
        path = tmp_path / "spline.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        splines = [s for s in snaps if s.entity_type == EntityType.SPLINE]
        assert len(splines) == 1
        assert len(splines[0].points) >= 2

    def test_hatch_extraction(self, tmp_path):
        """HATCH entities are extracted with boundary vertices."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        hatch = msp.add_hatch(color=1, dxfattribs={"layer": "L"})
        hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
        path = tmp_path / "hatch.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        hatches = [s for s in snaps if s.entity_type == EntityType.HATCH]
        assert len(hatches) == 1
        assert len(hatches[0].points) >= 3

    def test_polyline2d_extraction(self, tmp_path):
        """POLYLINE (2D) entities are extracted with vertices as points."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        msp.add_polyline2d([(0, 0), (10, 0), (10, 10)], dxfattribs={"layer": "L"})
        path = tmp_path / "polyline2d.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        polys = [s for s in snaps if s.entity_type == EntityType.POLYLINE]
        assert len(polys) == 1
        assert len(polys[0].points) >= 2

    def test_solid_extraction(self, tmp_path):
        """SOLID entities are extracted with vertex points."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        msp.add_solid([(0, 0), (5, 0), (5, 5), (0, 5)], dxfattribs={"layer": "L"})
        path = tmp_path / "solid.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        solids = [s for s in snaps if s.entity_type == EntityType.SOLID]
        assert len(solids) == 1
        assert len(solids[0].points) >= 3

    def test_dimension_extraction(self, tmp_path):
        """DIMENSION entities are extracted with at least one point."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        dim = msp.add_aligned_dim(p1=(0, 0), p2=(10, 0), distance=3, dxfattribs={"layer": "L"})
        dim.render()
        path = tmp_path / "dim.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        dims = [s for s in snaps if s.entity_type == EntityType.DIMENSION]
        assert len(dims) >= 1
        assert len(dims[0].points) >= 1

    def test_insert_extraction_records_block_name(self, tmp_path):
        """INSERT entities record block_name from the block reference."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        blk = doc.blocks.new("MY_BLK")
        blk.add_circle((0, 0), radius=1)
        msp.add_blockref("MY_BLK", insert=(20, 20), dxfattribs={"layer": "L"})
        path = tmp_path / "insert.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        inserts = [s for s in snaps if s.entity_type == EntityType.INSERT]
        assert len(inserts) == 1
        assert inserts[0].block_name == "MY_BLK"
        assert len(inserts[0].points) == 1

    def test_mtext_extraction(self, tmp_path):
        """MTEXT entities are extracted with text_content and insert point."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        msp.add_mtext("Hello MTEXT", dxfattribs={"layer": "L", "insert": (5, 5), "char_height": 2})
        path = tmp_path / "mtext.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        mtexts = [s for s in snaps if s.entity_type == EntityType.MTEXT]
        assert len(mtexts) == 1
        assert mtexts[0].text_content is not None
        assert len(mtexts[0].points) == 1

    def test_unknown_entity_type_excluded(self, tmp_path):
        """Entity types outside EntityType enum are silently skipped."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("L", color=1)
        # POINT is not in EntityType — should be skipped
        msp.add_point((1, 1), dxfattribs={"layer": "L"})
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "L"})
        path = tmp_path / "mixed.dxf"
        doc.saveas(str(path))

        snaps = extract_snapshots(path)
        types = {s.entity_type for s in snaps}
        # Only LINE should be present; POINT is not in _EXTRACTABLE_TYPES
        assert EntityType.LINE in types
        assert all(s.entity_type != "POINT" for s in snaps)


# ---------------------------------------------------------------------------
# Exception / fallback paths in _extract_one and _detect_xrefs_and_dynblocks
# ---------------------------------------------------------------------------


class TestExtractOneExceptionPaths:
    """Cover exception-handling branches in _extract_one (lines 339-419)."""

    def _base_entity(self, dxf_type: str):
        """Return a MagicMock that looks like a minimal DXF entity."""
        from unittest.mock import MagicMock

        entity = MagicMock()
        entity.dxf.handle = f"H_{dxf_type}"
        entity.dxf.layer = "LAYER0"
        return entity

    def test_polyline_vertex_exception_returns_none(self):
        """POLYLINE: exception during vertex iteration → return None (line 339-341)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("POLYLINE")
        # Make .vertices raise so the inner try/except triggers return None
        type(entity).vertices = PropertyMock(side_effect=Exception("vertex IO error"))
        result = _extract_one(entity, "POLYLINE")
        assert result is None

    def test_dimension_no_insert_no_defpoint_returns_none(self):
        """DIMENSION: insert raises AND defpoint raises → return None (lines 348-354)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        # Build a one-off class so we can set unique properties without
        # polluting the shared MagicMock type across test instances.
        class _DxfNoBoth:
            def get(self, name, default=None):
                return default

            @property
            def insert(self):
                raise AttributeError("no insert")

            @property
            def defpoint(self):
                raise AttributeError("no defpoint")

            @property
            def handle(self):
                return "H_DIMENSION"

            @property
            def layer(self):
                return "LAYER0"

        entity = MagicMock()
        entity.dxf = _DxfNoBoth()
        result = _extract_one(entity, "DIMENSION")
        assert result is None

    def test_dimension_insert_fails_defpoint_succeeds(self):
        """DIMENSION: insert raises but defpoint succeeds → returns a snapshot (lines 349-351)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        class _Coord:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class _DxfInsertFails:
            def get(self, name, default=None):
                return "LABEL"

            @property
            def insert(self):
                raise AttributeError("no insert")

            @property
            def defpoint(self):
                return _Coord(5.0, 10.0)

            @property
            def handle(self):
                return "H_DIMENSION"

            @property
            def layer(self):
                return "LAYER0"

        entity = MagicMock()
        entity.dxf = _DxfInsertFails()
        result = _extract_one(entity, "DIMENSION")
        # Should have fallen back to defpoint and produced a valid snapshot
        assert result is not None
        assert result.points[0].x == 5.0
        assert result.points[0].y == 10.0

    def test_spline_control_point_exception_returns_none(self):
        """SPLINE: control_points raises → return None (lines 367-369)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("SPLINE")
        type(entity).control_points = PropertyMock(side_effect=Exception("spline data corrupt"))
        result = _extract_one(entity, "SPLINE")
        assert result is None

    def test_hatch_boundary_exception_returns_none(self):
        """HATCH: boundary paths raise → no points → return None (lines 378-381)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("HATCH")
        type(entity).paths = PropertyMock(side_effect=Exception("hatch data missing"))
        result = _extract_one(entity, "HATCH")
        assert result is None

    def test_hatch_empty_vertices_returns_none(self):
        """HATCH: boundary with no vertices → empty points list → return None (line 381)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("HATCH")
        # paths is truthy but each sub-path has no vertices attribute
        path_obj = MagicMock()
        del path_obj.vertices  # ensure getattr(..., []) returns []
        entity.paths = [path_obj]
        result = _extract_one(entity, "HATCH")
        assert result is None

    def test_mleader_context_exception_returns_none(self):
        """MLEADER: context attribute raises → return None (lines 384-391)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("MLEADER")
        type(entity).context = PropertyMock(side_effect=Exception("MLEADER context error"))
        result = _extract_one(entity, "MLEADER")
        assert result is None

    def test_leader_vertex_exception_returns_none(self):
        """LEADER: vertices raises → return None (lines 394-399)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("LEADER")
        type(entity).vertices = PropertyMock(side_effect=Exception("leader data corrupt"))
        result = _extract_one(entity, "LEADER")
        assert result is None

    def test_solid_vertex_exception_returns_none(self):
        """SOLID: vtx.x access raises → return None (lines 407-409)."""
        from unittest.mock import MagicMock, PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        entity = self._base_entity("SOLID")
        # The code does: vtx = getattr(entity.dxf, attr, None); points.append(Point2D(x=vtx.x, ...))
        # We need vtx.x to raise.  Use PropertyMock on the vtx's *type* so access raises.
        vtx = MagicMock()
        type(vtx).x = PropertyMock(side_effect=Exception("bad vtx x"))
        # getattr(entity.dxf, "vtx0", None) must return our vtx
        entity.dxf.vtx0 = vtx
        result = _extract_one(entity, "SOLID")
        assert result is None

    def test_generic_outer_exception_returns_none(self):
        """Outer except in _extract_one catches unexpected errors → return None (lines 414-416)."""
        from unittest.mock import PropertyMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        # LINE branch — entity.dxf.start is attribute access, so use PropertyMock
        entity = self._base_entity("LINE")
        type(entity.dxf).start = PropertyMock(side_effect=RuntimeError("corrupted DXF data"))
        result = _extract_one(entity, "LINE")
        assert result is None

    def test_empty_points_after_extraction_returns_none(self):
        """Entity produces zero points (line 419) — INSERT with no insert coords."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _extract_one

        # Use an entity type that would normally work but trick it into empty points
        # by making insert.x / insert.y raise, which falls through to the outer except.
        # Easier: use MLEADER where context.mtext is falsy → no points appended.
        entity = self._base_entity("MLEADER")
        ctx = MagicMock()
        ctx.mtext = None  # falsy — no text branch taken, so points stays []
        entity.context = ctx
        result = _extract_one(entity, "MLEADER")
        assert result is None


class TestDetectXrefsAndDynblocksDirectly:
    """Cover _detect_xrefs_and_dynblocks branches via mock ezdxf documents."""

    def _make_block_layout(
        self,
        name: str,
        flags: int = 0,
        ext_dict_keys: list[str] | None = None,
        ext_dict_raises: bool = False,
        block_record_none: bool = False,
    ):
        """Build a mock block_layout object."""
        from unittest.mock import MagicMock

        layout = MagicMock()
        layout.name = name

        if block_record_none:
            layout.block = None
            return layout

        block_record = MagicMock()
        block_record.dxf.get.return_value = flags

        if ext_dict_raises:
            type(block_record).extension_dict = property(
                lambda self: (_ for _ in ()).throw(Exception("ext dict IO error"))
            )
        elif ext_dict_keys is not None:
            xdict = MagicMock()
            xdict.__contains__ = lambda self, key: key in ext_dict_keys
            block_record.extension_dict = xdict
        else:
            # No extension dict keys
            xdict = MagicMock()
            xdict.__contains__ = lambda self, key: False
            block_record.extension_dict = xdict

        layout.block = block_record
        return layout

    def test_block_record_none_is_skipped(self):
        """block_record is None → continue without error (line 250)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks

        doc = MagicMock()
        doc.blocks = [
            self._make_block_layout("NULL_BLOCK", block_record_none=True),
            self._make_block_layout("NORMAL", flags=0),
        ]
        warnings = _detect_xrefs_and_dynblocks(doc, [], "test")
        # No crash, no warnings (no xrefs/dynblocks among real blocks)
        assert warnings == []

    def test_extension_dict_exception_is_swallowed(self):
        """extension_dict access raises → logged, no crash, block skipped (lines 261-263)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks

        doc = MagicMock()
        doc.blocks = [self._make_block_layout("BAD_EXT", ext_dict_raises=True)]
        # Should not raise — exception is caught inside _detect_xrefs_and_dynblocks
        warnings = _detect_xrefs_and_dynblocks(doc, [], "")
        assert isinstance(warnings, list)

    def test_xref_block_produces_warning(self):
        """Block with BLK_XREF flag (bit 4) + matching INSERT → xref warning (lines 269-274)."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks
        from cad_dxf_agent.models.cad_schema import EntityType, Point2D
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        doc = MagicMock()
        doc.blocks = [self._make_block_layout("XREF_A", flags=4)]

        snap = GeometrySnapshot(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="0",
            points=[Point2D(x=0, y=0)],
            block_name="XREF_A",
        )
        warnings = _detect_xrefs_and_dynblocks(doc, [snap], "master")
        assert len(warnings) == 1
        assert "external reference" in warnings[0]
        assert "XREF_A" in warnings[0]
        assert warnings[0].startswith("master: ")

    def test_dynblock_produces_warning(self):
        """Block with ACAD_ENHANCEDBLOCK in ext dict + INSERT → dynblock warning."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks
        from cad_dxf_agent.models.cad_schema import EntityType, Point2D
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        doc = MagicMock()
        doc.blocks = [
            self._make_block_layout("DYN_B", flags=0, ext_dict_keys=["ACAD_ENHANCEDBLOCK"])
        ]

        snap = GeometrySnapshot(
            handle="I2",
            entity_type=EntityType.INSERT,
            layer="0",
            points=[Point2D(x=10, y=10)],
            block_name="DYN_B",
        )
        warnings = _detect_xrefs_and_dynblocks(doc, [snap], "")
        assert len(warnings) == 1
        assert "dynamic block" in warnings[0]
        assert "DYN_B" in warnings[0]

    def test_xref_and_dynblock_both_produce_two_warnings(self):
        """One xref block + one dynblock each referenced by an INSERT → two warnings."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks
        from cad_dxf_agent.models.cad_schema import EntityType, Point2D
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        doc = MagicMock()
        doc.blocks = [
            self._make_block_layout("XREF_GRID", flags=4),
            self._make_block_layout("DYN_COL", flags=0, ext_dict_keys=["ACAD_ENHANCEDBLOCK"]),
        ]

        snaps = [
            GeometrySnapshot(
                handle="I1",
                entity_type=EntityType.INSERT,
                layer="0",
                points=[Point2D(x=0, y=0)],
                block_name="XREF_GRID",
            ),
            GeometrySnapshot(
                handle="I2",
                entity_type=EntityType.INSERT,
                layer="0",
                points=[Point2D(x=5, y=5)],
                block_name="DYN_COL",
            ),
        ]
        warnings = _detect_xrefs_and_dynblocks(doc, snaps, "revision")
        assert len(warnings) == 2
        xref_w = [w for w in warnings if "external reference" in w]
        dyn_w = [w for w in warnings if "dynamic block" in w]
        assert len(xref_w) == 1
        assert len(dyn_w) == 1
        assert "XREF_GRID" in xref_w[0]
        assert "DYN_COL" in dyn_w[0]

    def test_no_matching_inserts_no_warnings(self):
        """Xref block defined but no INSERT snapshot references it → no warning."""
        from unittest.mock import MagicMock

        from cad_dxf_agent.core.comparison.geometry import _detect_xrefs_and_dynblocks
        from cad_dxf_agent.models.cad_schema import EntityType, Point2D
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        doc = MagicMock()
        doc.blocks = [self._make_block_layout("UNUSED_XREF", flags=4)]

        # INSERT references a *different* block name — xref_count stays 0
        snap = GeometrySnapshot(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="0",
            points=[Point2D(x=0, y=0)],
            block_name="SOMETHING_ELSE",
        )
        warnings = _detect_xrefs_and_dynblocks(doc, [snap], "")
        assert warnings == []
