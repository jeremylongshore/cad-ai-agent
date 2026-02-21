"""Tests for the tool executor — CAD tool dispatch and operation accumulation."""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.tool_executor import ToolExecutor
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)


@pytest.fixture
def drawing_context():
    """Minimal drawing context for tool executor tests."""
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="A1",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
                insert_point=Point2D(x=0, y=0),
            ),
            EntityRef(
                handle="A2",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=10, y=10),
                text_content="Column C-4",
            ),
            EntityRef(
                handle="A3",
                entity_type=EntityType.INSERT,
                layer="STRUCTURAL",
                insert_point=Point2D(x=25, y=25),
                block_name="COLUMN_MARK",
            ),
            EntityRef(
                handle="A4",
                entity_type=EntityType.TEXT,
                layer="TITLE",
                insert_point=Point2D(x=0, y=-20),
                text_content="PROJECT TITLE",
            ),
        ],
        layers=[
            LayerRule(name="STRUCTURAL", protected=False),
            LayerRule(name="NOTES", protected=False),
            LayerRule(name="TITLE", protected=True),
        ],
        blocks=["COLUMN_MARK"],
    )


@pytest.fixture
def executor(drawing_context):
    """ToolExecutor with protected layers set."""
    return ToolExecutor(
        drawing_context, protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]
    )


class TestQueryTools:
    def test_find_entities_all(self, executor):
        result = executor.execute("find_entities", {})
        assert result["count"] == 4

    def test_find_entities_by_layer(self, executor):
        result = executor.execute("find_entities", {"layer": "STRUCTURAL"})
        assert result["count"] == 2

    def test_find_entities_by_type(self, executor):
        result = executor.execute("find_entities", {"entity_type": "TEXT"})
        assert result["count"] == 2

    def test_find_entities_by_text(self, executor):
        result = executor.execute("find_entities", {"text_contains": "Column"})
        assert result["count"] == 1
        assert result["entities"][0]["handle"] == "A2"

    def test_find_entities_combined_filters(self, executor):
        result = executor.execute(
            "find_entities",
            {
                "layer": "NOTES",
                "entity_type": "TEXT",
                "text_contains": "Column",
            },
        )
        assert result["count"] == 1

    def test_get_entity_found(self, executor):
        result = executor.execute("get_entity", {"handle": "A1"})
        assert result["handle"] == "A1"
        assert result["type"] == "LINE"
        assert result["layer"] == "STRUCTURAL"

    def test_get_entity_not_found(self, executor):
        result = executor.execute("get_entity", {"handle": "ZZZZZ"})
        assert "error" in result

    def test_find_nearest(self, executor):
        result = executor.execute("find_nearest", {"x": 9, "y": 9})
        assert result["handle"] == "A2"

    def test_find_nearest_with_type_filter(self, executor):
        result = executor.execute("find_nearest", {"x": 9, "y": 9, "entity_type": "LINE"})
        assert result["handle"] == "A1"

    def test_list_layers(self, executor):
        result = executor.execute("list_layers", {})
        assert len(result["layers"]) == 3
        layer_names = {lyr["name"] for lyr in result["layers"]}
        assert "STRUCTURAL" in layer_names

    def test_is_protected_true(self, executor):
        result = executor.execute("is_protected", {"layer": "TITLE"})
        assert result["protected"] is True

    def test_is_protected_false(self, executor):
        result = executor.execute("is_protected", {"layer": "STRUCTURAL"})
        assert result["protected"] is False


class TestEditTools:
    def test_move_entity_queues_operation(self, executor):
        result = executor.execute("move_entity", {"handle": "A1", "dx": 24.0, "dy": 0.0})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == "move_entity"
        assert op.target_handle == "A1"
        assert op.params == {"dx": 24.0, "dy": 0.0}

    def test_move_entity_protected_blocked(self, executor):
        result = executor.execute("move_entity", {"handle": "A4", "dx": 1, "dy": 0})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_move_entity_not_found(self, executor):
        result = executor.execute("move_entity", {"handle": "ZZZ", "dx": 1, "dy": 0})
        assert "error" in result

    def test_edit_text_queues_operation(self, executor):
        result = executor.execute("edit_text", {"handle": "A2", "new_text": "Updated"})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == "edit_text"
        assert op.params["new_text"] == "Updated"

    def test_edit_text_protected_blocked(self, executor):
        result = executor.execute("edit_text", {"handle": "A4", "new_text": "Hacked"})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_delete_entity_queues_operation(self, executor):
        result = executor.execute("delete_entity", {"handle": "A1"})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        assert executor.operations[0].op_type == "delete_entity"

    def test_delete_entity_protected_blocked(self, executor):
        result = executor.execute("delete_entity", {"handle": "A4"})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_add_block_queues_operation(self, executor):
        result = executor.execute(
            "add_block",
            {
                "block_name": "COLUMN_MARK",
                "x": 50,
                "y": 50,
            },
        )
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == "add_block"
        assert op.params["block_name"] == "COLUMN_MARK"

    def test_add_block_protected_layer_blocked(self, executor):
        result = executor.execute(
            "add_block",
            {
                "block_name": "COLUMN_MARK",
                "x": 0,
                "y": 0,
                "layer": "TITLE",
            },
        )
        assert "error" in result
        assert len(executor.operations) == 0

    def test_multiple_operations_accumulate(self, executor):
        executor.execute("move_entity", {"handle": "A1", "dx": 10, "dy": 0})
        executor.execute("edit_text", {"handle": "A2", "new_text": "New"})
        executor.execute("delete_entity", {"handle": "A3"})
        assert len(executor.operations) == 3


class TestUnknownTool:
    def test_unknown_tool_raises(self, executor):
        with pytest.raises(KeyError, match="Unknown tool"):
            executor.execute("fly_to_moon", {})
