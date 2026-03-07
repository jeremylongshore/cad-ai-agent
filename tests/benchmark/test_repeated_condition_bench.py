"""Micro-benchmarks for repeated-condition detection.

Uses pytest-benchmark to measure ConditionDetector.find_repeated()
on a realistic structural drawing. Run with: pytest tests/benchmark/ -v

Baseline expectation: <500ms for a 200-entity drawing.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.repeated_condition import ConditionDetector
from cad_dxf_agent.models.cad_schema import EntityType
from tests.helpers.dxf_factory import create_structural_drawing

pytestmark = pytest.mark.benchmark


class TestRepeatedConditionBench:
    """Benchmarks for ConditionDetector.find_repeated() at different scales."""

    def test_find_repeated_structural(self, tmp_path, benchmark):
        """200-entity structural drawing — the primary target scenario."""
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        # Use the first INSERT (COLUMN_MARK block) as exemplar
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        assert len(inserts) >= 2, "structural drawing should have multiple block inserts"
        exemplar_handles = [inserts[0].handle]

        detector = ConditionDetector(ctx)
        result = benchmark(detector.find_repeated, exemplar_handles)
        # Sanity: should find other column marks
        assert result.total_found >= 1

    def test_find_repeated_multi_entity_exemplar(self, tmp_path, benchmark):
        """Multi-entity exemplar (block + nearby text)."""
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        texts = [e for e in ctx.entities if e.entity_type == EntityType.TEXT]
        assert inserts and texts
        exemplar_handles = [inserts[0].handle, texts[0].handle]

        detector = ConditionDetector(ctx)
        benchmark(detector.find_repeated, exemplar_handles)

    def test_find_repeated_large_drawing(self, tmp_path, benchmark):
        """8x6 grid → ~500 entities — tests scaling."""
        dxf_path = create_structural_drawing(
            tmp_path, grid_cols=8, grid_rows=6, filename="large_structural.dxf"
        )
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        assert len(inserts) >= 2
        exemplar_handles = [inserts[0].handle]

        detector = ConditionDetector(ctx)
        result = benchmark(detector.find_repeated, exemplar_handles)
        assert result.total_found >= 1

    def test_find_repeated_no_matches(self, tmp_path, benchmark):
        """Exemplar with unique text — expect zero candidates (fast path)."""
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        # Use a protected-layer entity that has no peers
        title_entities = [e for e in ctx.entities if e.layer.upper() == "TITLE"]
        if not title_entities:
            pytest.skip("no TITLE entities in structural drawing")
        exemplar_handles = [title_entities[0].handle]

        detector = ConditionDetector(ctx)
        benchmark(detector.find_repeated, exemplar_handles)
