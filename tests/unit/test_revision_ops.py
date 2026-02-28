"""Tests for revision_ops: EntityChange → RevisionOp conversion."""

from __future__ import annotations

from cad_dxf_agent.core.comparison.revision_ops import (
    comparison_result_to_ops,
    entity_change_to_ops,
)
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    MatchMethod,
    RevisionOpType,
)
from tests.helpers.comparison_factory import make_comparison_result, make_entity_change


class TestEntityChangeToOps:
    """entity_change_to_ops produces correct ops per category."""

    def test_unchanged_produces_no_ops(self):
        change = make_entity_change(ChangeCategory.UNCHANGED)
        ops = entity_change_to_ops(change, 0)
        assert ops == []

    def test_moved_produces_move_op(self):
        change = make_entity_change(
            ChangeCategory.MOVED,
            displacement=(10.0, 5.0),
            confidence=0.9,
            match_method=MatchMethod.fingerprint,
        )
        ops = entity_change_to_ops(change, 3)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.MOVE
        assert op.change_index == 3
        assert op.forward == {"dx": 10.0, "dy": 5.0}
        assert op.reverse == {"dx": -10.0, "dy": -5.0}
        assert op.confidence == 0.9
        assert op.match_method == MatchMethod.fingerprint

    def test_removed_produces_delete_op(self):
        change = make_entity_change(
            ChangeCategory.REMOVED,
            master_handle="FF",
            layer="NOTES",
            entity_type=EntityType.TEXT,
            master_text="old note",
        )
        ops = entity_change_to_ops(change, 1)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.DELETE
        assert op.target_handle == "FF"
        assert op.target_layer == "NOTES"
        assert op.forward == {}
        assert "snapshot" in op.reverse
        assert op.reverse["snapshot"]["text_content"] == "old note"

    def test_added_produces_add_op(self):
        change = make_entity_change(
            ChangeCategory.ADDED,
            revision_handle="CC",
            layer="STRUCTURAL",
            revision_points=[(5, 5), (15, 15)],
        )
        ops = entity_change_to_ops(change, 2)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.ADD
        assert op.target_handle == "CC"
        assert "snapshot" in op.forward
        assert op.reverse == {}

    def test_modified_text_produces_modify_text_op(self):
        change = make_entity_change(
            ChangeCategory.MODIFIED,
            entity_type=EntityType.TEXT,
            master_text="REV A",
            revision_text="REV B",
            modifications={"text_content": {"from": "REV A", "to": "REV B"}},
        )
        ops = entity_change_to_ops(change, 0)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.MODIFY_TEXT
        assert op.forward == {"new_text": "REV B"}
        assert op.reverse == {"new_text": "REV A"}

    def test_modified_geometry_produces_modify_geometry_op(self):
        change = make_entity_change(
            ChangeCategory.MODIFIED,
            entity_type=EntityType.LWPOLYLINE,
            master_points=[(0, 0), (10, 0), (10, 10)],
            revision_points=[(0, 0), (15, 0), (15, 15)],
            modifications={
                "point_count": {"from": 3, "to": 3},
                "changed_point_indices": {"from": [1, 2], "to": [1, 2]},
            },
        )
        ops = entity_change_to_ops(change, 0)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.MODIFY_GEOMETRY
        assert len(op.forward["new_points"]) == 3
        assert len(op.reverse["new_points"]) == 3

    def test_modified_attributes_produces_modify_attributes_op(self):
        change = make_entity_change(
            ChangeCategory.MODIFIED,
            master_attributes={"radius": 10},
            revision_attributes={"radius": 15},
            modifications={"radius": {"from": 10, "to": 15}},
        )
        ops = entity_change_to_ops(change, 0)
        assert len(ops) == 1
        op = ops[0]
        assert op.op_type == RevisionOpType.MODIFY_ATTRIBUTES
        assert op.forward == {"radius": 15}
        assert op.reverse == {"radius": 10}

    def test_compound_modified_produces_multiple_ops(self):
        """A MODIFIED change with both text and geometry changes emits 2 ops."""
        change = make_entity_change(
            ChangeCategory.MODIFIED,
            entity_type=EntityType.TEXT,
            master_text="A",
            revision_text="B",
            master_points=[(0, 0)],
            revision_points=[(5, 5)],
            modifications={
                "text_content": {"from": "A", "to": "B"},
                "changed_point_indices": {"from": [0], "to": [0]},
            },
        )
        ops = entity_change_to_ops(change, 0)
        assert len(ops) == 2
        types = {op.op_type for op in ops}
        assert types == {RevisionOpType.MODIFY_TEXT, RevisionOpType.MODIFY_GEOMETRY}

    def test_op_ids_are_unique(self):
        change = make_entity_change(
            ChangeCategory.MODIFIED,
            entity_type=EntityType.TEXT,
            master_text="A",
            revision_text="B",
            modifications={
                "text_content": {"from": "A", "to": "B"},
                "changed_point_indices": {"from": [0], "to": [0]},
            },
        )
        ops = entity_change_to_ops(change, 0)
        ids = [op.op_id for op in ops]
        assert len(ids) == len(set(ids))

    def test_confidence_propagated(self):
        change = make_entity_change(
            ChangeCategory.MOVED,
            displacement=(1, 2),
            confidence=0.73,
        )
        ops = entity_change_to_ops(change, 0)
        assert ops[0].confidence == 0.73


class TestComparisonResultToOps:
    """comparison_result_to_ops processes full result sets."""

    def test_empty_result(self):
        result = make_comparison_result([])
        ops = comparison_result_to_ops(result)
        assert ops == []

    def test_mixed_changes(self):
        changes = [
            make_entity_change(ChangeCategory.UNCHANGED),
            make_entity_change(ChangeCategory.MOVED, displacement=(5, 0), master_handle="A1"),
            make_entity_change(ChangeCategory.REMOVED, master_handle="A2"),
            make_entity_change(
                ChangeCategory.ADDED, revision_handle="B3", revision_points=[(1, 1)]
            ),
        ]
        result = make_comparison_result(changes)
        ops = comparison_result_to_ops(result)
        # 0 (unchanged) + 1 (moved) + 1 (removed) + 1 (added) = 3
        assert len(ops) == 3
        assert ops[0].change_index == 1  # moved
        assert ops[1].change_index == 2  # removed
        assert ops[2].change_index == 3  # added
