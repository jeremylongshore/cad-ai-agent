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
