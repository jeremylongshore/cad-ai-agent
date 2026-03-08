"""Tests for batch operations — bulk edit tools with filter criteria.

Covers all 5 batch tools (batch_move, batch_rotate, batch_scale,
batch_delete, batch_edit_text), filter resolution, protected layer
exclusion, and error handling.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.tool_executor import ToolExecutor
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
)
from cad_dxf_agent.models.ops_schema import OpType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ent(
    handle: str,
    etype: EntityType,
    layer: str = "STRUCTURAL",
    x: float = 0,
    y: float = 0,
    text: str | None = None,
    text_height: float | None = None,
) -> EntityRef:
    point = Point2D(x=x, y=y)
    tg = TextGeometry(height=text_height) if text_height else None
    return EntityRef(
        handle=handle,
        entity_type=etype,
        layer=layer,
        insert_point=point,
        text_content=text,
        text_geometry=tg,
    )


def _ctx(entities: list[EntityRef], layers: list[str] | None = None):
    layer_names = layers or list({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _executor(ctx, protected=None):
    return ToolExecutor(ctx, protected_layers=protected or [])


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mixed_drawing():
    """Drawing with lines on STRUCTURAL, text on NOTES, inserts on MARKS."""
    return _ctx([
        _ent("L1", EntityType.LINE, "STRUCTURAL", 0, 0),
        _ent("L2", EntityType.LINE, "STRUCTURAL", 10, 0),
        _ent("L3", EntityType.LINE, "STRUCTURAL", 20, 0),
        _ent("T1", EntityType.TEXT, "NOTES", 5, 5, text="Room A"),
        _ent("T2", EntityType.TEXT, "NOTES", 15, 5, text="Room B"),
        _ent("T3", EntityType.MTEXT, "NOTES", 25, 5, text="Room C"),
        _ent("I1", EntityType.INSERT, "MARKS", 50, 50),
        _ent("I2", EntityType.INSERT, "MARKS", 60, 50),
    ])


# ===================================================================
# Tests: Filter resolution
# ===================================================================


class TestBatchFilterResolution:
    """Test the _resolve_batch_filter shared method."""

    def test_no_filter_returns_error(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {"dx": 5, "dy": 0})
        assert "error" in result
        assert "filter" in result["error"].lower()

    def test_filter_by_layer(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 5, "dy": 0,
        })
        assert result["status"] == "queued"
        assert result["matched"] == 3
        assert len(exe.operations) == 3
        for op in exe.operations:
            assert op.op_type == OpType.MOVE_ENTITY

    def test_filter_by_entity_type(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "entity_type": "TEXT", "dx": 0, "dy": 10,
        })
        assert result["matched"] == 2  # T1, T2 (not MTEXT T3)

    def test_filter_by_text_contains(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "text_contains": "Room", "dx": 1, "dy": 1,
        })
        # All 3 text entities contain "Room"
        assert result["matched"] == 3

    def test_filter_by_radius(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "center_x": 55, "center_y": 50, "radius": 10,
            "dx": 0, "dy": 5,
        })
        # I1 at (50,50) and I2 at (60,50) are within radius 10 of (55,50)
        assert result["matched"] == 2

    def test_combined_filters(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "layer": "NOTES", "entity_type": "TEXT",
            "dx": 0, "dy": 5,
        })
        # Only TEXT on NOTES: T1, T2 (not T3 which is MTEXT)
        assert result["matched"] == 2

    def test_no_matches_returns_error(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "layer": "NONEXISTENT", "dx": 1, "dy": 1,
        })
        assert "error" in result
        assert "No matching" in result["error"]

    def test_protected_layers_excluded(self, mixed_drawing):
        exe = _executor(mixed_drawing, protected=["TITLE", "NOTES"])
        result = exe.execute("batch_move", {
            "layer": "NOTES", "dx": 1, "dy": 1,
        })
        # All NOTES entities excluded by protection
        assert "error" in result
        assert "No matching" in result["error"]


# ===================================================================
# Tests: batch_move
# ===================================================================


class TestBatchMove:
    """Test batch_move tool."""

    def test_basic_batch_move(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 10, "dy": -5,
        })
        assert result["status"] == "queued"
        assert result["matched"] == 3
        assert result["dx"] == 10
        assert result["dy"] == -5

        for op in exe.operations:
            assert op.op_type == OpType.MOVE_ENTITY
            assert op.params["dx"] == 10
            assert op.params["dy"] == -5

    def test_batch_move_preserves_entity_metadata(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 1, "dy": 1,
        })
        handles = {op.target_handle for op in exe.operations}
        assert handles == {"L1", "L2", "L3"}


# ===================================================================
# Tests: batch_rotate
# ===================================================================


class TestBatchRotate:
    """Test batch_rotate tool."""

    def test_basic_batch_rotate(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_rotate", {
            "layer": "STRUCTURAL", "angle": 90,
        })
        assert result["matched"] == 3
        assert result["angle"] == 90

        for op in exe.operations:
            assert op.op_type == OpType.ROTATE_ENTITY
            assert op.params["angle"] == 90

    def test_batch_rotate_with_shared_center(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        exe.execute("batch_rotate", {
            "layer": "STRUCTURAL", "angle": 45,
            "cx": 100, "cy": 200,
        })
        for op in exe.operations:
            assert op.params["cx"] == 100
            assert op.params["cy"] == 200

    def test_batch_rotate_uses_entity_center(self, mixed_drawing):
        """Without cx/cy, each entity rotates around its own center."""
        exe = _executor(mixed_drawing)
        exe.execute("batch_rotate", {
            "layer": "STRUCTURAL", "angle": 30,
        })
        # L1 at (0,0), L2 at (10,0), L3 at (20,0)
        centers = [(op.params["cx"], op.params["cy"]) for op in exe.operations]
        assert (0, 0) in centers
        assert (10, 0) in centers
        assert (20, 0) in centers


# ===================================================================
# Tests: batch_scale
# ===================================================================


class TestBatchScale:
    """Test batch_scale tool."""

    def test_basic_batch_scale(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_scale", {
            "layer": "MARKS", "factor": 2.0,
        })
        assert result["matched"] == 2
        assert result["factor"] == 2.0

        for op in exe.operations:
            assert op.op_type == OpType.SCALE_ENTITY
            assert op.params["factor"] == 2.0

    def test_batch_scale_with_shared_center(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        exe.execute("batch_scale", {
            "layer": "MARKS", "factor": 0.5,
            "cx": 55, "cy": 50,
        })
        for op in exe.operations:
            assert op.params["cx"] == 55
            assert op.params["cy"] == 50


# ===================================================================
# Tests: batch_delete
# ===================================================================


class TestBatchDelete:
    """Test batch_delete tool."""

    def test_basic_batch_delete(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_delete", {
            "layer": "MARKS",
        })
        assert result["matched"] == 2
        assert len(exe.operations) == 2
        for op in exe.operations:
            assert op.op_type == OpType.DELETE_ENTITY

    def test_batch_delete_by_type(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_delete", {
            "entity_type": "INSERT",
        })
        assert result["matched"] == 2

    def test_batch_delete_requires_filter(self, mixed_drawing):
        """batch_delete without any filter should fail."""
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_delete", {})
        assert "error" in result


# ===================================================================
# Tests: batch_edit_text
# ===================================================================


class TestBatchEditText:
    """Test batch_edit_text tool."""

    def test_basic_find_replace(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_edit_text", {
            "layer": "NOTES",
            "find": "Room",
            "replace": "Space",
        })
        assert result["matched"] == 3
        assert result["find"] == "Room"
        assert result["replace"] == "Space"

        for op in exe.operations:
            assert op.op_type == OpType.EDIT_TEXT
            assert "Space" in op.params["new_text"]

    def test_find_replace_partial_match(self, mixed_drawing):
        """Only entities containing the find string get edited."""
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_edit_text", {
            "text_contains": "Room A",
            "find": "A",
            "replace": "1",
        })
        assert result["matched"] == 1
        assert exe.operations[0].params["new_text"] == "Room 1"

    def test_find_not_found_returns_error(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_edit_text", {
            "layer": "NOTES",
            "find": "NONEXISTENT",
            "replace": "X",
        })
        assert "error" in result

    def test_non_text_entities_excluded(self, mixed_drawing):
        """batch_edit_text should only affect TEXT/MTEXT, not LINE etc."""
        exe = _executor(mixed_drawing)
        result = exe.execute("batch_edit_text", {
            "layer": "STRUCTURAL",
            "find": "foo",
            "replace": "bar",
        })
        # No TEXT/MTEXT on STRUCTURAL layer
        assert "error" in result


# ===================================================================
# Tests: Tool definition presence
# ===================================================================


class TestBatchToolDefinitions:
    """Verify batch tools are registered in tool_definitions."""

    def test_batch_tools_in_edit_tools(self):
        from cad_dxf_agent.llm.tool_definitions import EDIT_TOOLS

        names = {t["name"] for t in EDIT_TOOLS}
        assert "batch_move" in names
        assert "batch_rotate" in names
        assert "batch_scale" in names
        assert "batch_delete" in names
        assert "batch_edit_text" in names

    def test_batch_tools_in_all_tools(self):
        from cad_dxf_agent.llm.tool_definitions import ALL_TOOLS

        names = {t["name"] for t in ALL_TOOLS}
        assert "batch_move" in names
        assert "batch_edit_text" in names

    def test_batch_tools_are_edit_tools(self):
        from cad_dxf_agent.llm.tool_definitions import is_edit_tool

        assert is_edit_tool("batch_move")
        assert is_edit_tool("batch_rotate")
        assert is_edit_tool("batch_scale")
        assert is_edit_tool("batch_delete")
        assert is_edit_tool("batch_edit_text")

    def test_batch_tool_schemas_valid(self):
        from cad_dxf_agent.llm.tool_definitions import get_tool_by_name

        for name in [
            "batch_move", "batch_rotate", "batch_scale",
            "batch_delete", "batch_edit_text",
        ]:
            tool = get_tool_by_name(name)
            assert tool is not None, f"Tool {name} not found"
            assert "parameters" in tool
            assert tool["parameters"]["type"] == "object"


# ===================================================================
# Tests: Edge cases
# ===================================================================


class TestBatchEdgeCases:
    """Test edge cases and interactions."""

    def test_batch_ops_mix_with_individual_ops(self, mixed_drawing):
        """Batch and individual ops accumulate in the same operation list."""
        exe = _executor(mixed_drawing)

        # Individual op first
        exe.execute("move_entity", {"handle": "L1", "dx": 1, "dy": 1})

        # Then batch op
        exe.execute("batch_move", {
            "layer": "NOTES", "dx": 5, "dy": 5,
        })

        # Should have 1 individual + 3 batch = 4 total
        assert len(exe.operations) == 4

    def test_multiple_batch_ops_accumulate(self, mixed_drawing):
        exe = _executor(mixed_drawing)
        exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 1, "dy": 0,
        })
        exe.execute("batch_rotate", {
            "layer": "NOTES", "angle": 45,
        })
        # 3 moves + 3 rotates = 6
        assert len(exe.operations) == 6

    def test_empty_drawing_returns_error(self):
        ctx = _ctx([], layers=["STRUCTURAL"])
        exe = _executor(ctx)
        result = exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 1, "dy": 1,
        })
        assert "error" in result

    def test_batch_operations_preserve_space(self, mixed_drawing):
        """Operations should preserve the entity's space attribute."""
        exe = _executor(mixed_drawing)
        exe.execute("batch_move", {
            "layer": "STRUCTURAL", "dx": 1, "dy": 0,
        })
        for op in exe.operations:
            assert op.target_space == "Model"
