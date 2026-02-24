"""Tests for the deterministic planner pattern matching."""

from __future__ import annotations

from cad_dxf_agent.llm.deterministic_planner import deterministic_plan
from cad_dxf_agent.models.ops_schema import OpType

# Shared drawing context with known handles
SAMPLE_CONTEXT = {
    "entities": [
        {"handle": "A1", "type": "LINE", "layer": "STRUCTURAL"},
        {"handle": "B2", "type": "TEXT", "layer": "NOTES", "text": "Grid A"},
        {"handle": "C3", "type": "INSERT", "layer": "STRUCTURAL", "block_name": "COLUMN"},
    ],
    "layers": [
        {"name": "STRUCTURAL", "protected": False},
        {"name": "NOTES", "protected": False},
    ],
    "blocks": ["COLUMN"],
}


class TestDeterministicDelete:
    def test_delete_by_handle(self):
        result = deterministic_plan("delete entity A1", SAMPLE_CONTEXT)
        assert result is not None
        assert result.op_count == 1
        assert result.operations[0].op_type == OpType.DELETE_ENTITY
        assert result.operations[0].target_handle == "A1"

    def test_delete_case_insensitive(self):
        result = deterministic_plan("Delete Entity a1", SAMPLE_CONTEXT)
        assert result is not None
        assert result.operations[0].target_handle == "A1"

    def test_delete_unknown_handle_returns_none(self):
        result = deterministic_plan("delete entity ZZ99", SAMPLE_CONTEXT)
        assert result is None


class TestDeterministicMove:
    def test_move_by_offset(self):
        result = deterministic_plan("move A1 by (10.5, -3.0)", SAMPLE_CONTEXT)
        assert result is not None
        assert result.op_count == 1
        op = result.operations[0]
        assert op.op_type == OpType.MOVE_ENTITY
        assert op.target_handle == "A1"
        assert op.params["dx"] == 10.5
        assert op.params["dy"] == -3.0

    def test_move_integer_offsets(self):
        result = deterministic_plan("move B2 by (24, 0)", SAMPLE_CONTEXT)
        assert result is not None
        assert result.operations[0].params["dx"] == 24.0
        assert result.operations[0].params["dy"] == 0.0

    def test_move_unknown_handle_returns_none(self):
        result = deterministic_plan("move ZZ by (1, 1)", SAMPLE_CONTEXT)
        assert result is None


class TestDeterministicEditText:
    def test_edit_text_single_quotes(self):
        result = deterministic_plan("change text of B2 to 'New Label'", SAMPLE_CONTEXT)
        assert result is not None
        assert result.op_count == 1
        op = result.operations[0]
        assert op.op_type == OpType.EDIT_TEXT
        assert op.target_handle == "B2"
        assert op.params["new_text"] == "New Label"

    def test_edit_text_double_quotes(self):
        result = deterministic_plan('change text of B2 to "Updated"', SAMPLE_CONTEXT)
        assert result is not None
        assert result.operations[0].params["new_text"] == "Updated"

    def test_edit_text_unknown_handle_returns_none(self):
        result = deterministic_plan("change text of ZZ to 'test'", SAMPLE_CONTEXT)
        assert result is None


class TestDeterministicFallback:
    def test_natural_language_returns_none(self):
        result = deterministic_plan("move the footing near grid C-4 two feet east", SAMPLE_CONTEXT)
        assert result is None

    def test_empty_prompt_returns_none(self):
        result = deterministic_plan("", SAMPLE_CONTEXT)
        assert result is None

    def test_complex_prompt_returns_none(self):
        result = deterministic_plan("delete all lines on the STRUCTURAL layer", SAMPLE_CONTEXT)
        assert result is None

    def test_empty_context_returns_none(self):
        result = deterministic_plan("delete entity A1", {"entities": []})
        assert result is None

    def test_revision_label_set(self):
        result = deterministic_plan("delete entity A1", SAMPLE_CONTEXT)
        assert result is not None
        assert result.revision_label is not None
        assert "Deterministic" in result.revision_label
