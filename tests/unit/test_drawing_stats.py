"""Tests for drawing statistics computation."""

from __future__ import annotations

from pathlib import Path

from cad_dxf_agent.core.context_builder import drawing_stats
from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.models.stats_schema import DrawingStats
from tests.helpers.dxf_factory import (
    create_empty_dxf,
    create_minimal_dxf,
    create_structural_drawing,
)


class TestDrawingStats:
    def test_stats_from_structural_drawing(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert isinstance(stats, DrawingStats)
        assert stats.file_name == "structural.dxf"
        assert stats.file_size_bytes > 0
        assert stats.dxf_version == "AC1032"  # R2018
        assert stats.entity_count > 0
        assert stats.editable_entity_count > 0
        assert stats.editable_entity_count <= stats.entity_count
        assert stats.layer_count > 0
        assert stats.layout_count >= 1  # At least Model
        assert stats.block_count >= 1  # COLUMN_MARK
        assert len(stats.counts_by_type) > 0
        assert len(stats.counts_by_layer) > 0
        assert stats.coverage_pct > 0

    def test_stats_protected_layers(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx, protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"])

        assert "TITLE" in stats.protected_layers
        assert stats.editable_entity_count < stats.entity_count

    def test_stats_from_minimal_drawing(self, tmp_path: Path):
        dxf_path = create_minimal_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert stats.entity_count == 1
        assert stats.editable_entity_count == 1
        assert stats.counts_by_type.get("LINE") == 1

    def test_stats_from_empty_drawing(self, tmp_path: Path):
        dxf_path = create_empty_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert stats.entity_count == 0
        assert stats.editable_entity_count == 0
        assert stats.coverage_pct == 100.0  # No types at all → 100%

    def test_bounding_box_computed(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert stats.bounding_box is not None
        mn, mx = stats.bounding_box
        assert mn.x <= mx.x
        assert mn.y <= mx.y

    def test_bounding_box_none_for_empty(self, tmp_path: Path):
        dxf_path = create_empty_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert stats.bounding_box is None

    def test_load_warnings_propagated(self, tmp_path: Path):
        dxf_path = create_empty_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)

        assert len(stats.load_warnings) > 0
        codes = [w.code for w in stats.load_warnings]
        assert "EMPTY_DRAWING" in codes
