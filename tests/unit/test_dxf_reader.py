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
