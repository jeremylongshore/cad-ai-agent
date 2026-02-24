"""Tests for support report formatting."""

from __future__ import annotations

from pathlib import Path

from cad_dxf_agent.core.context_builder import drawing_stats, support_report
from cad_dxf_agent.core.dxf_reader import load_dxf
from tests.helpers.dxf_factory import create_structural_drawing


class TestSupportReport:
    def test_report_contains_file_info(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert "structural.dxf" in report
        assert "DXF Version" in report
        assert "bytes" in report

    def test_report_contains_entity_counts(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert "Entities:" in report
        assert "editable" in report
        assert "total" in report

    def test_report_contains_layer_info(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx, protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"])
        report = support_report(stats)

        assert "Layers:" in report
        assert "PROTECTED" in report

    def test_report_contains_entity_types(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert "Entity Types:" in report
        assert "LINE" in report

    def test_report_contains_bounding_box(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert "Bounding Box" in report

    def test_report_contains_coverage(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert "Type Coverage:" in report
        assert "%" in report

    def test_report_is_multiline_string(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert isinstance(report, str)
        assert len(report.splitlines()) > 10

    def test_report_header(self, tmp_path: Path):
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        stats = drawing_stats(ctx)
        report = support_report(stats)

        assert report.startswith("Drawing Support Report")
