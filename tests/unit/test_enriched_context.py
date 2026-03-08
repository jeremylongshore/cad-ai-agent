"""Tests for family-aware enriched context builder."""

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_enriched_context


@pytest.fixture
def structural_dxf(tmp_path: Path) -> Path:
    """Create a structural-style DXF."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("COLUMN_GRID", color=2)
    doc.layers.add("BEAM", color=3)
    doc.layers.add("NOTES", color=4)
    doc.layers.add("TITLE", color=7)

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_line((0, 0), (0, 100), dxfattribs={"layer": "COLUMN_GRID"})
    msp.add_text(
        "Column C-4",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )
    msp.add_text(
        "Beam B-12",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (20, 20)},
    )
    msp.add_text(
        "Foundation note",
        dxfattribs={"layer": "NOTES", "height": 2.0, "insert": (30, 30)},
    )

    path = tmp_path / "structural.dxf"
    doc.saveas(path)
    return path


class TestBuildEnrichedContext:
    def test_has_document_family(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        assert "document_family" in result
        assert "family" in result["document_family"]
        assert "confidence" in result["document_family"]

    def test_detects_structural_family(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        family = result["document_family"]["family"]
        assert family == "structural"

    def test_has_primitives(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        assert "primitives" in result
        primitives = result["primitives"]
        assert "symbols" in primitives
        assert "labels" in primitives
        assert "layer_classification" in primitives
        assert "entity_counts" in primitives

    def test_has_base_context_fields(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        # Base planner context fields still present
        assert "entities" in result
        assert "layers" in result
        assert "entity_count" in result

    def test_labels_populated(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        labels = result["primitives"]["labels"]
        assert labels["total_labels"] >= 3

    def test_layer_classification(self, structural_dxf):
        ctx = load_dxf(str(structural_dxf))
        result = build_enriched_context(ctx)
        lc = result["primitives"]["layer_classification"]
        assert "STRUCTURAL" in lc["structural"]
