"""Tests for plan_to_changeset converter (EPIC-CAD-07)."""

from __future__ import annotations

from cad_dxf_agent.core.plan_converter import plan_to_changeset
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D
from cad_dxf_agent.models.ops_schema import OpType
from cad_dxf_agent.models.plan_schema import (
    ActionValidationDetail,
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(*actions: EditAction, prompt: str = "test prompt") -> EditPlan:
    """Build a minimal EditPlan wrapping the given actions."""
    return EditPlan(actions=list(actions), prompt=prompt)


def _make_action(
    action_type: EditActionType,
    handle: str = "H1",
    layer: str | None = None,
    params: dict | None = None,
    *,
    blocked: bool = False,
) -> EditAction:
    """Build an EditAction with optional BLOCKED validation status."""
    validation = ActionValidationDetail(
        status=PlanValidationStatus.BLOCKED if blocked else PlanValidationStatus.VALID
    )
    return EditAction(
        action_type=action_type,
        target_handle=handle,
        target_layer=layer,
        params=params or {},
        validation=validation,
    )


def _context_with_insert(handle: str, block_name: str, layer: str = "NOTES") -> DrawingContext:
    """Return a DrawingContext containing one INSERT entity."""
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle=handle,
                entity_type=EntityType.INSERT,
                layer=layer,
                block_name=block_name,
                insert_point=Point2D(x=10, y=20),
            )
        ],
    )


# ---------------------------------------------------------------------------
# 1. Empty plan → empty changeset
# ---------------------------------------------------------------------------


def test_empty_plan_returns_empty_changeset():
    plan = _make_plan()
    changeset, index_map = plan_to_changeset(plan)

    assert changeset.op_count == 0
    assert index_map == {}


# ---------------------------------------------------------------------------
# 2. MOVE_ENTITY → move_entity with dx, dy
# ---------------------------------------------------------------------------


def test_move_action_converts_op_type_and_params():
    action = _make_action(EditActionType.MOVE_ENTITY, handle="A1", params={"dx": 5.0, "dy": -3.0})
    changeset, _ = plan_to_changeset(_make_plan(action))

    assert changeset.op_count == 1
    op = changeset.operations[0]
    assert op.op_type == OpType.MOVE_ENTITY
    assert op.target_handle == "A1"
    assert op.params["dx"] == 5.0
    assert op.params["dy"] == -3.0


# ---------------------------------------------------------------------------
# 3. EDIT_TEXT → edit_text with new_text
# ---------------------------------------------------------------------------


def test_edit_text_action_converts_op_type_and_params():
    action = _make_action(
        EditActionType.EDIT_TEXT, handle="T1", params={"new_text": "Revised Note"}
    )
    changeset, _ = plan_to_changeset(_make_plan(action))

    assert changeset.op_count == 1
    op = changeset.operations[0]
    assert op.op_type == OpType.EDIT_TEXT
    assert op.target_handle == "T1"
    assert op.params["new_text"] == "Revised Note"


# ---------------------------------------------------------------------------
# 4. DELETE_ENTITY → delete_entity with no required params
# ---------------------------------------------------------------------------


def test_delete_action_converts_correctly():
    action = _make_action(EditActionType.DELETE_ENTITY, handle="D1")
    changeset, _ = plan_to_changeset(_make_plan(action))

    assert changeset.op_count == 1
    op = changeset.operations[0]
    assert op.op_type == OpType.DELETE_ENTITY
    assert op.target_handle == "D1"


# ---------------------------------------------------------------------------
# 5. ADD_BLOCK → add_block with block_name and insert_point
# ---------------------------------------------------------------------------


def test_add_block_action_converts_correctly():
    action = _make_action(
        EditActionType.ADD_BLOCK,
        handle="I1",
        params={"block_name": "DETAIL_A", "insert_point": {"x": 10.0, "y": 20.0}},
    )
    changeset, _ = plan_to_changeset(_make_plan(action))

    assert changeset.op_count == 1
    op = changeset.operations[0]
    assert op.op_type == OpType.ADD_BLOCK
    assert op.params["block_name"] == "DETAIL_A"
    assert op.params["insert_point"] == {"x": 10.0, "y": 20.0}


# ---------------------------------------------------------------------------
# 6. REPLICATE_NOTE → add_block, block_name resolved from context
# ---------------------------------------------------------------------------


def test_replicate_note_resolves_block_name_from_context():
    context = _context_with_insert(handle="SRC1", block_name="MARK_X")
    action = _make_action(
        EditActionType.REPLICATE_NOTE,
        handle="SRC1",
        params={
            "source_handles": ["SRC1"],
            "target_centroid": {"x": 50.0, "y": 60.0},
        },
    )
    changeset, _ = plan_to_changeset(_make_plan(action), context=context)

    assert changeset.op_count == 1
    op = changeset.operations[0]
    assert op.op_type == OpType.ADD_BLOCK
    assert op.params["block_name"] == "MARK_X"
    assert op.params["insert_point"] == {"x": 50.0, "y": 60.0}


# ---------------------------------------------------------------------------
# 7. REPLICATE_NOTE without context → empty block_name
# ---------------------------------------------------------------------------


def test_replicate_note_without_context_yields_empty_block_name():
    action = _make_action(
        EditActionType.REPLICATE_NOTE,
        params={
            "source_handles": ["SRC1"],
            "target_centroid": {"x": 1.0, "y": 2.0},
        },
    )
    changeset, _ = plan_to_changeset(_make_plan(action), context=None)

    assert changeset.op_count == 1
    assert changeset.operations[0].params["block_name"] == ""


# ---------------------------------------------------------------------------
# 8. Order preserved across multiple actions
# ---------------------------------------------------------------------------


def test_multiple_actions_preserve_order():
    actions = [
        _make_action(EditActionType.MOVE_ENTITY, handle="M1", params={"dx": 1.0, "dy": 0.0}),
        _make_action(EditActionType.EDIT_TEXT, handle="T1", params={"new_text": "A"}),
        _make_action(EditActionType.DELETE_ENTITY, handle="D1"),
    ]
    changeset, _ = plan_to_changeset(_make_plan(*actions))

    assert changeset.op_count == 3
    assert changeset.operations[0].target_handle == "M1"
    assert changeset.operations[1].target_handle == "T1"
    assert changeset.operations[2].target_handle == "D1"


# ---------------------------------------------------------------------------
# 9. Blocked action is skipped
# ---------------------------------------------------------------------------


def test_blocked_action_is_skipped():
    action = _make_action(EditActionType.MOVE_ENTITY, handle="BLK", blocked=True)
    changeset, index_map = plan_to_changeset(_make_plan(action))

    assert changeset.op_count == 0
    assert index_map == {}


# ---------------------------------------------------------------------------
# 10. Mixed blocked and valid actions → only valid ones in changeset
# ---------------------------------------------------------------------------


def test_mixed_blocked_and_valid_only_includes_valid():
    valid_action = _make_action(EditActionType.DELETE_ENTITY, handle="KEEP")
    blocked_action = _make_action(EditActionType.EDIT_TEXT, handle="SKIP", blocked=True)
    changeset, _ = plan_to_changeset(_make_plan(valid_action, blocked_action))

    assert changeset.op_count == 1
    assert changeset.operations[0].target_handle == "KEEP"


# ---------------------------------------------------------------------------
# 11. action_index_map is correct when actions are skipped
# ---------------------------------------------------------------------------


def test_action_index_map_accounts_for_skipped_actions():
    # action indices: 0=blocked, 1=valid, 2=valid
    blocked = _make_action(EditActionType.MOVE_ENTITY, handle="BLK", blocked=True)
    first_valid = _make_action(EditActionType.DELETE_ENTITY, handle="V1")
    second_valid = _make_action(EditActionType.DELETE_ENTITY, handle="V2")

    _, index_map = plan_to_changeset(_make_plan(blocked, first_valid, second_valid))

    # op index 0 → action index 1, op index 1 → action index 2
    assert index_map == {0: 1, 1: 2}


# ---------------------------------------------------------------------------
# 12. Prompt is forwarded from plan to changeset
# ---------------------------------------------------------------------------


def test_prompt_forwarded_to_changeset():
    plan = _make_plan(prompt="move the wall left 5")
    changeset, _ = plan_to_changeset(plan)

    assert changeset.prompt == "move the wall left 5"


# ---------------------------------------------------------------------------
# 13. Multiple actions of the same type
# ---------------------------------------------------------------------------


def test_multiple_actions_same_type():
    actions = [
        _make_action(EditActionType.EDIT_TEXT, handle=f"T{i}", params={"new_text": f"Note {i}"})
        for i in range(4)
    ]
    changeset, index_map = plan_to_changeset(_make_plan(*actions))

    assert changeset.op_count == 4
    for op_idx, action_idx in index_map.items():
        assert op_idx == action_idx  # no skips, indices are identical
    handles = [op.target_handle for op in changeset.operations]
    assert handles == ["T0", "T1", "T2", "T3"]


# ---------------------------------------------------------------------------
# 14. Plan with all five action types
# ---------------------------------------------------------------------------


def test_plan_with_all_action_types():
    context = _context_with_insert(handle="SRC", block_name="BLK_Y")
    actions = [
        _make_action(EditActionType.MOVE_ENTITY, handle="M1", params={"dx": 1.0, "dy": 0.0}),
        _make_action(EditActionType.EDIT_TEXT, handle="T1", params={"new_text": "X"}),
        _make_action(EditActionType.DELETE_ENTITY, handle="D1"),
        _make_action(
            EditActionType.ADD_BLOCK,
            handle="I1",
            params={"block_name": "BLK_A", "insert_point": {"x": 0.0, "y": 0.0}},
        ),
        _make_action(
            EditActionType.REPLICATE_NOTE,
            handle="SRC",
            params={"source_handles": ["SRC"], "target_centroid": {"x": 5.0, "y": 5.0}},
        ),
    ]
    changeset, index_map = plan_to_changeset(_make_plan(*actions), context=context)

    assert changeset.op_count == 5
    assert index_map == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}

    op_types = [op.op_type for op in changeset.operations]
    assert op_types == [
        OpType.MOVE_ENTITY,
        OpType.EDIT_TEXT,
        OpType.DELETE_ENTITY,
        OpType.ADD_BLOCK,
        OpType.ADD_BLOCK,  # REPLICATE_NOTE maps to ADD_BLOCK
    ]

    # REPLICATE_NOTE resolved the block name from context
    assert changeset.operations[4].params["block_name"] == "BLK_Y"


# ---------------------------------------------------------------------------
# 15. REPLICATE_NOTE with block_name already in params skips context lookup
# ---------------------------------------------------------------------------


def test_replicate_note_with_explicit_block_name_skips_context_lookup():
    # Context has a different block_name for the same handle — should be ignored
    context = _context_with_insert(handle="SRC", block_name="CONTEXT_BLOCK")
    action = _make_action(
        EditActionType.REPLICATE_NOTE,
        handle="SRC",
        params={
            "source_handles": ["SRC"],
            "block_name": "EXPLICIT_BLOCK",  # already provided
            "target_centroid": {"x": 7.0, "y": 8.0},
        },
    )
    changeset, _ = plan_to_changeset(_make_plan(action), context=context)

    op = changeset.operations[0]
    assert op.params["block_name"] == "EXPLICIT_BLOCK"
    assert op.params["insert_point"] == {"x": 7.0, "y": 8.0}
