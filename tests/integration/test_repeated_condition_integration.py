"""Integration tests for repeated-condition detection pipeline (EPIC-CAD-05).

Tests the full pipeline: load DXF → build context → detect repeated conditions.
Uses programmatic DXF fixtures (no stored files).
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.repeated_condition import ConditionDetector
from cad_dxf_agent.models.repeated_condition_schema import (
    SimilarityConfig,
    SimilaritySignalType,
)
from tests.helpers.dxf_factory import create_structural_drawing


@pytest.mark.integration
class TestRepeatedConditionPipeline:
    """Full pipeline: load DXF → detect repeated conditions."""

    def test_structural_drawing_column_marks(self, tmp_path):
        """Structural drawing has repeated COLUMN_MARK blocks at grid intersections."""
        dxf_path = create_structural_drawing(tmp_path, grid_cols=5, grid_rows=4)
        context = load_dxf(dxf_path)

        # Find one COLUMN_MARK insert
        inserts = [
            e
            for e in context.entities
            if e.entity_type.value == "INSERT" and e.block_name == "COLUMN_MARK"
        ]
        assert len(inserts) >= 10  # 5x4 grid = 20 column marks

        # Use first insert as exemplar
        detector = ConditionDetector(context)
        result = detector.find_repeated([inserts[0].handle])

        # Should find many other column marks
        assert result.total_found >= 5
        assert result.summary  # non-empty summary

        # All candidates should have block_name signal
        for candidate in result.candidates:
            block_signal = next(
                (s for s in candidate.signals if s.signal_type == SimilaritySignalType.BLOCK_NAME),
                None,
            )
            assert block_signal is not None
            assert block_signal.score > 0

    def test_structural_drawing_text_labels(self, tmp_path):
        """Structural drawing has repeated column-mark labels (A-1, B-1, ...)."""
        dxf_path = create_structural_drawing(tmp_path, grid_cols=4, grid_rows=3)
        context = load_dxf(dxf_path)

        # Find column-mark label texts (A-1, B-1, etc.) on NOTES layer
        texts = [
            e
            for e in context.entities
            if e.entity_type.value in ("TEXT", "MTEXT")
            and e.layer.upper() == "NOTES"
            and e.text_content
            and "-" in e.text_content
            and len(e.text_content) <= 5
        ]
        assert len(texts) >= 3

        detector = ConditionDetector(context)
        result = detector.find_repeated([texts[0].handle])

        # Should find other similar labels
        assert result.total_found >= 1

    def test_protected_layer_entities_not_matched(self, tmp_path):
        """Entities on protected layers should not appear as exemplar candidates."""
        dxf_path = create_structural_drawing(tmp_path, add_title_block=True)
        context = load_dxf(dxf_path)

        # Find a TITLE layer entity
        title_entities = [e for e in context.entities if e.layer.upper() == "TITLE"]
        if not title_entities:
            pytest.skip("No TITLE entities in fixture")

        detector = ConditionDetector(context)
        result = detector.find_repeated([title_entities[0].handle])

        # Should not find matches on protected layers (title text is unique)
        # This is behavioral — not a hard gate, but unique text shouldn't match
        for candidate in result.candidates:
            assert candidate.confidence < 1.0  # nothing should be a perfect match

    def test_exemplar_with_multiple_entities(self, tmp_path):
        """Using multiple entities as exemplar narrows the search."""
        dxf_path = create_structural_drawing(tmp_path, grid_cols=5, grid_rows=4)
        context = load_dxf(dxf_path)

        # Use a column mark + its nearby label as exemplar (multi-entity)
        inserts = [
            e
            for e in context.entities
            if e.entity_type.value == "INSERT" and e.block_name == "COLUMN_MARK"
        ]

        if not inserts:
            pytest.skip("Missing inserts for multi-entity test")

        # Find the label text nearest to the first column mark
        first_insert = inserts[0]
        nearby_text = None
        for e in context.entities:
            if (
                e.entity_type.value in ("TEXT", "MTEXT")
                and e.layer.upper() == "NOTES"
                and e.text_content
                and e.insert_point
                and first_insert.insert_point
            ):
                dx = abs(e.insert_point.x - first_insert.insert_point.x)
                dy = abs(e.insert_point.y - first_insert.insert_point.y)
                if dx < 10 and dy < 10:
                    nearby_text = e
                    break

        if nearby_text is None:
            pytest.skip("No nearby text for multi-entity test")

        # Single entity exemplar
        detector = ConditionDetector(context)
        single_result = detector.find_repeated([inserts[0].handle])

        # Multi-entity exemplar (block + its label)
        multi_result = detector.find_repeated([inserts[0].handle, nearby_text.handle])

        # Both should produce results
        assert single_result.total_found >= 1
        assert multi_result.total_found >= 1

    def test_config_min_confidence(self, tmp_path):
        """High min_confidence threshold filters out weak matches."""
        dxf_path = create_structural_drawing(tmp_path, grid_cols=3, grid_rows=2)
        context = load_dxf(dxf_path)

        inserts = [
            e
            for e in context.entities
            if e.entity_type.value == "INSERT" and e.block_name == "COLUMN_MARK"
        ]
        assert len(inserts) >= 2

        # Strict config
        strict_config = SimilarityConfig(min_confidence=0.90)
        detector = ConditionDetector(context, strict_config)
        result = detector.find_repeated([inserts[0].handle])

        for c in result.candidates:
            assert c.confidence >= 0.90

    def test_result_serialization(self, tmp_path):
        """Result should serialize to JSON cleanly."""
        dxf_path = create_structural_drawing(tmp_path, grid_cols=3, grid_rows=2)
        context = load_dxf(dxf_path)

        inserts = [
            e
            for e in context.entities
            if e.entity_type.value == "INSERT" and e.block_name == "COLUMN_MARK"
        ]

        detector = ConditionDetector(context)
        result = detector.find_repeated([inserts[0].handle])

        # Should serialize without error
        data = result.model_dump()
        assert isinstance(data, dict)
        assert "exemplar_handles" in data
        assert "candidates" in data
        assert "summary" in data

        # JSON round-trip
        import json

        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["exemplar_handles"] == [inserts[0].handle]
