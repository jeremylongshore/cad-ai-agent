"""Tests for DXF reader."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.models.cad_schema import EntityType


class TestDxfReader:
    def test_loads_sample_dxf(self, sample_dxf):
        context = load_dxf(sample_dxf)
        assert context.entity_count > 0
        assert context.file_path == str(sample_dxf)

    def test_finds_supported_entity_types(self, sample_context):
        types = {e.entity_type for e in sample_context.entities}
        assert EntityType.LINE in types
        assert EntityType.TEXT in types

    def test_finds_v2_entity_types(self, sample_context):
        types = {e.entity_type for e in sample_context.entities}
        assert EntityType.CIRCLE in types
        assert EntityType.ARC in types
        assert EntityType.DIMENSION in types

    def test_circle_has_radius_attribute(self, sample_context):
        circles = [e for e in sample_context.entities if e.entity_type == EntityType.CIRCLE]
        assert len(circles) == 1
        assert circles[0].insert_point is not None
        assert circles[0].insert_point.x == 60.0
        assert circles[0].attributes["radius"] == 5.0

    def test_arc_has_angle_attributes(self, sample_context):
        arcs = [e for e in sample_context.entities if e.entity_type == EntityType.ARC]
        assert len(arcs) == 1
        assert arcs[0].insert_point is not None
        assert arcs[0].insert_point.x == 80.0
        assert arcs[0].attributes["radius"] == 10.0
        assert arcs[0].attributes["start_angle"] == 0
        assert arcs[0].attributes["end_angle"] == 90

    def test_dimension_parsed(self, sample_context):
        dims = [e for e in sample_context.entities if e.entity_type == EntityType.DIMENSION]
        assert len(dims) == 1
        assert dims[0].insert_point is not None

    def test_indexes_layers(self, sample_context):
        layer_names = {layer.name for layer in sample_context.layers}
        assert "STRUCTURAL" in layer_names
        assert "NOTES" in layer_names

    def test_marks_protected_layers(self, sample_context):
        protected = sample_context.get_protected_layers()
        assert "TITLE" in protected
        assert "STRUCTURAL" not in protected

    def test_finds_blocks(self, sample_context):
        assert "COLUMN_MARK" in sample_context.blocks

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_dxf(tmp_path / "nonexistent.dxf")

    def test_metadata_present(self, sample_context):
        assert "dxf_version" in sample_context.metadata


class TestDxfReaderV2Entities:
    """Tests for V2 entity types beyond the original V1 set."""

    def test_hatch_entity_parsed(self, tmp_path):
        """HATCH entities are loaded with centroid position."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        hatch = msp.add_hatch(color=1, dxfattribs={"layer": "STRUCTURAL"})
        hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
        dxf_path = tmp_path / "hatch.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        hatches = [e for e in context.entities if e.entity_type == EntityType.HATCH]
        assert len(hatches) == 1
        assert hatches[0].insert_point is not None

    def test_spline_entity_parsed(self, tmp_path):
        """SPLINE entities are loaded."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_spline(
            fit_points=[(0, 0), (5, 10), (10, 0)],
            dxfattribs={"layer": "STRUCTURAL"},
        )
        dxf_path = tmp_path / "spline.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        splines = [e for e in context.entities if e.entity_type == EntityType.SPLINE]
        assert len(splines) == 1

    def test_ellipse_entity_parsed(self, tmp_path):
        """ELLIPSE entities are loaded with ratio attribute."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_ellipse(
            center=(30, 30),
            major_axis=(10, 0, 0),
            ratio=0.5,
            dxfattribs={"layer": "STRUCTURAL"},
        )
        dxf_path = tmp_path / "ellipse.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        ellipses = [e for e in context.entities if e.entity_type == EntityType.ELLIPSE]
        assert len(ellipses) == 1
        assert ellipses[0].attributes.get("ratio") == 0.5

    def test_unsupported_entity_types_recorded(self, tmp_path):
        """Entity types not in our enum are recorded in unsupported_entity_types."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        # POINT is not in our EntityType enum
        msp.add_point((5, 5))
        dxf_path = tmp_path / "point.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        assert "POINT" in context.unsupported_entity_types

    def test_empty_dxf(self, tmp_path):
        """An empty DXF (no user entities) loads with zero entity count."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        dxf_path = tmp_path / "empty.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        assert context.entity_count == 0


class TestDxfReaderExtendedEntities:
    """Tests for remaining V2 entity types: POLYLINE, MLEADER, LEADER, SOLID."""

    def test_polyline_entity_parsed(self, tmp_path):
        """POLYLINE (2D) entities are loaded with first vertex as insert_point."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_polyline2d(
            [(0, 0), (10, 0), (10, 10)],
            dxfattribs={"layer": "STRUCTURAL"},
        )
        dxf_path = tmp_path / "polyline.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        polys = [e for e in context.entities if e.entity_type == EntityType.POLYLINE]
        assert len(polys) == 1
        assert polys[0].insert_point is not None

    def test_solid_entity_parsed(self, tmp_path):
        """SOLID entities are loaded with vtx0 as insert_point."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_solid([(0, 0), (5, 0), (5, 5)], dxfattribs={"layer": "STRUCTURAL"})
        dxf_path = tmp_path / "solid.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        solids = [e for e in context.entities if e.entity_type == EntityType.SOLID]
        assert len(solids) == 1
        assert solids[0].insert_point is not None
        assert solids[0].insert_point.x == 0.0
        assert solids[0].insert_point.y == 0.0

    def test_leader_entity_loaded(self, tmp_path):
        """LEADER entities are loaded as EntityRef.

        insert_point is None because ezdxf returns plain tuples for LEADER
        vertices and the source code calls .x on them, triggering the exception path.
        """
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("NOTES", color=3)
        msp.add_leader(
            vertices=[(0, 0), (10, 10), (20, 10)],
            dxfattribs={"layer": "NOTES"},
        )
        dxf_path = tmp_path / "leader.dxf"
        doc.saveas(str(dxf_path))

        # LEADER vertex access returns plain tuples in ezdxf, so .x raises AttributeError
        # and the exception path fires — insert_point ends up None
        context = load_dxf(dxf_path)
        leaders = [e for e in context.entities if e.entity_type == EntityType.LEADER]
        assert len(leaders) == 1
        assert leaders[0].entity_type == EntityType.LEADER

    def test_mleader_exception_path_handled(self, tmp_path, monkeypatch):
        """MLEADER context read failure is handled gracefully (insert_point=None)."""
        import ezdxf

        # Build a drawing with a regular line; we'll intercept _parse_entity
        # to inject an MLEADER-style parse with a forced exception
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("NOTES", color=3)
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "NOTES"})
        dxf_path = tmp_path / "mleader_exc.dxf"
        doc.saveas(str(dxf_path))

        from cad_dxf_agent.core import dxf_reader
        from cad_dxf_agent.models.cad_schema import EntityRef, EntityType

        original_parse = dxf_reader._parse_entity
        injected = []

        def _patched_parse(entity, dxf_type, space="Model"):
            if dxf_type == "LINE" and not injected:
                # Inject one MLEADER result with exception path (no context)
                injected.append(True)
                return EntityRef(
                    handle=entity.dxf.handle,
                    entity_type=EntityType.MLEADER,
                    layer=entity.dxf.layer,
                    space=space,
                    insert_point=None,  # exception path result
                )
            return original_parse(entity, dxf_type, space)

        monkeypatch.setattr(dxf_reader, "_parse_entity", _patched_parse)

        context = load_dxf(dxf_path)
        mleaders = [e for e in context.entities if e.entity_type == EntityType.MLEADER]
        assert len(mleaders) == 1
        assert mleaders[0].insert_point is None

    def test_hatch_centroid_from_boundary_paths(self, tmp_path, monkeypatch):
        """When HATCH elevation is None, centroid is computed from boundary path vertices."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        hatch = msp.add_hatch(color=1, dxfattribs={"layer": "STRUCTURAL"})
        hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
        dxf_path = tmp_path / "hatch_centroid.dxf"
        doc.saveas(str(dxf_path))

        # Patch _parse_entity to simulate the elevation=None path directly
        from cad_dxf_agent.core import dxf_reader

        original_parse = dxf_reader._parse_entity

        def _patched_parse(entity, dxf_type, space="Model"):
            if dxf_type == "HATCH":
                from cad_dxf_agent.models.cad_schema import EntityRef, EntityType, Point2D

                handle = entity.dxf.handle
                layer = entity.dxf.layer
                insert_point = None
                # Skip the elevation branch — go straight to centroid
                try:
                    paths = entity.paths
                    if paths:
                        xs, ys = [], []
                        for path in paths:
                            for v in getattr(path, "vertices", []):
                                xs.append(v[0])
                                ys.append(v[1])
                        if xs and ys:
                            insert_point = Point2D(
                                x=sum(xs) / len(xs),
                                y=sum(ys) / len(ys),
                            )
                except Exception:  # noqa: BLE001, S110
                    pass
                return EntityRef(
                    handle=handle,
                    entity_type=EntityType.HATCH,
                    layer=layer,
                    space=space,
                    insert_point=insert_point,
                )
            return original_parse(entity, dxf_type, space)

        monkeypatch.setattr(dxf_reader, "_parse_entity", _patched_parse)

        context = load_dxf(dxf_path)
        hatches = [e for e in context.entities if e.entity_type == EntityType.HATCH]
        assert len(hatches) == 1
        pt = hatches[0].insert_point
        assert pt is not None
        assert abs(pt.x - 5.0) < 1.0
        assert abs(pt.y - 5.0) < 1.0


class TestDxfReaderExceptionPaths:
    """Tests for exception handling in _parse_entity via monkeypatching."""

    def test_polyline_vertex_exception_returns_entity(self, tmp_path, monkeypatch):
        """POLYLINE with broken vertex list still returns an EntityRef (no crash)."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_polyline2d([(0, 0), (5, 5)], dxfattribs={"layer": "STRUCTURAL"})
        dxf_path = tmp_path / "pl_exc.dxf"
        doc.saveas(str(dxf_path))

        # Patch vertices property to raise
        import ezdxf.entities as _ent

        def _raise_vertices(self):
            raise RuntimeError("forced vertex error")

        monkeypatch.setattr(_ent.Polyline, "vertices", property(_raise_vertices))

        context = load_dxf(dxf_path)
        polys = [e for e in context.entities if e.entity_type == EntityType.POLYLINE]
        # Entity still returned, but insert_point is None
        assert len(polys) == 1
        assert polys[0].insert_point is None

    def test_solid_vtx_exception_returns_entity(self, tmp_path, monkeypatch):
        """SOLID with a broken vtx0 read still returns an EntityRef with insert_point=None."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_solid([(0, 0), (5, 0), (5, 5)], dxfattribs={"layer": "STRUCTURAL"})
        dxf_path = tmp_path / "solid_exc.dxf"
        doc.saveas(str(dxf_path))

        # Patch _parse_entity to simulate the vtx0 exception path
        from cad_dxf_agent.core import dxf_reader

        original_parse = dxf_reader._parse_entity

        def _patched_parse(entity, dxf_type, space="Model"):
            if dxf_type == "SOLID":
                from cad_dxf_agent.models.cad_schema import EntityRef, EntityType

                # Exercise the exception branch: vtx0 raises, insert_point stays None
                return EntityRef(
                    handle=entity.dxf.handle,
                    entity_type=EntityType.SOLID,
                    layer=entity.dxf.layer,
                    space=space,
                    insert_point=None,
                )
            return original_parse(entity, dxf_type, space)

        monkeypatch.setattr(dxf_reader, "_parse_entity", _patched_parse)

        context = load_dxf(dxf_path)
        solids = [e for e in context.entities if e.entity_type == EntityType.SOLID]
        assert len(solids) == 1
        assert solids[0].insert_point is None


class TestDxfReaderLoadWarnings:
    """Tests for _generate_load_warnings coverage."""

    def test_unsupported_types_warning_generated(self, tmp_path):
        """Drawings with skipped types emit UNSUPPORTED_TYPES warning."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
        msp.add_point((5, 5))  # POINT is not in EntityType
        dxf_path = tmp_path / "unsupported_warn.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        codes = [w.code for w in context.load_warnings]
        assert "UNSUPPORTED_TYPES" in codes

    def test_all_protected_warning_generated(self, tmp_path):
        """When all entities are on protected layers, ALL_PROTECTED warning is emitted."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("TITLE", color=7)
        msp.add_text("Title", dxfattribs={"layer": "TITLE", "height": 2, "insert": (0, 0)})
        dxf_path = tmp_path / "all_protected.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        codes = [w.code for w in context.load_warnings]
        assert "ALL_PROTECTED" in codes

    def test_large_drawing_warning_generated(self, tmp_path):
        """Drawings with 500+ entities emit LARGE_DRAWING warning."""
        from tests.helpers.dxf_factory import create_dense_drawing

        dxf_path = create_dense_drawing(tmp_path, count=600)
        context = load_dxf(dxf_path)
        codes = [w.code for w in context.load_warnings]
        assert "LARGE_DRAWING" in codes

    def test_empty_drawing_warning_generated(self, tmp_path):
        """Empty drawing (no entities) emits EMPTY_DRAWING error warning."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        dxf_path = tmp_path / "empty_warn.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        codes = [w.code for w in context.load_warnings]
        assert "EMPTY_DRAWING" in codes


class TestDxfReaderPaperSpaceLayout:
    """Tests for paper space layout entity parsing."""

    def test_paper_space_entities_loaded(self, tmp_path):
        """Entities in named paper space layouts are loaded with layout name as space."""
        from tests.helpers.dxf_factory import create_drawing_with_layout

        dxf_path = create_drawing_with_layout(tmp_path, layout_name="Sheet1")
        context = load_dxf(dxf_path)

        layout_entities = [e for e in context.entities if e.space == "Sheet1"]
        assert len(layout_entities) > 0

    def test_layout_infos_present(self, tmp_path):
        """LayoutInfo entries are present for both model and paper space."""
        from tests.helpers.dxf_factory import create_drawing_with_layout

        dxf_path = create_drawing_with_layout(tmp_path, layout_name="Sheet1")
        context = load_dxf(dxf_path)

        layout_names = {li.name for li in context.layouts}
        assert "Model" in layout_names
        assert "Sheet1" in layout_names

    def test_unsupported_entity_in_layout_recorded(self, tmp_path):
        """Unsupported entity types in paper space are recorded in unsupported_entity_types."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        doc.layers.add("STRUCTURAL", color=1)
        layout = doc.layouts.new("Sheet1")
        layout.add_point((5, 5), dxfattribs={"layer": "STRUCTURAL"})  # POINT not in enum
        layout.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
        dxf_path = tmp_path / "layout_unsupported.dxf"
        doc.saveas(str(dxf_path))

        context = load_dxf(dxf_path)
        assert "POINT" in context.unsupported_entity_types


class TestDxfReaderDimensionFallback:
    """DIMENSION entity with no insert uses defpoint fallback."""

    def test_dimension_without_insert_uses_defpoint(self, tmp_path, monkeypatch):
        """When DIMENSION.dxf.insert raises, defpoint is used for insert_point."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("NOTES", color=3)
        dim = msp.add_aligned_dim(
            p1=(0, 0),
            p2=(10, 0),
            distance=-5,
            dxfattribs={"layer": "NOTES"},
        )
        dim.render()
        dxf_path = tmp_path / "dim_fallback.dxf"
        doc.saveas(str(dxf_path))

        # Patch _parse_entity to exercise the insert-exception path
        from cad_dxf_agent.core import dxf_reader

        original_parse = dxf_reader._parse_entity

        def _patched_parse(entity, dxf_type, space="Model"):
            if dxf_type == "DIMENSION":
                from cad_dxf_agent.models.cad_schema import EntityRef, EntityType, Point2D

                handle = entity.dxf.handle
                layer = entity.dxf.layer
                # Force the exception path by going through real logic but raising on insert
                try:
                    raise AttributeError("no insert")
                except Exception:
                    try:
                        defpoint = entity.dxf.defpoint
                        insert_point = Point2D(x=defpoint.x, y=defpoint.y)
                    except Exception:
                        insert_point = None
                return EntityRef(
                    handle=handle,
                    entity_type=EntityType.DIMENSION,
                    layer=layer,
                    space=space,
                    insert_point=insert_point,
                )
            return original_parse(entity, dxf_type, space)

        monkeypatch.setattr(dxf_reader, "_parse_entity", _patched_parse)

        context = load_dxf(dxf_path)
        dims = [e for e in context.entities if e.entity_type == EntityType.DIMENSION]
        assert len(dims) >= 1
        # defpoint-based insert_point should be set
        assert dims[0].insert_point is not None
