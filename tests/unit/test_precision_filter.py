"""Tests for precision_filter — entity filtering, delta overrides, and action details."""

from __future__ import annotations

from cad_dxf_agent.core.precision_filter import (
    apply_entity_filter,
    apply_exact_delta,
    build_action_details,
    build_match_candidates,
    check_confidence_threshold,
    parse_precision_controls,
)
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType
from cad_dxf_agent.models.precision_schema import ActionStatus, PrecisionControls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entity(
    handle: str,
    entity_type: EntityType = EntityType.LINE,
    layer: str = "WALLS",
    space: str = "Model",
    x: float | None = None,
    y: float | None = None,
    text: str | None = None,
) -> EntityRef:
    insert_point = Point2D(x=x, y=y) if x is not None and y is not None else None
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        space=space,
        insert_point=insert_point,
        text_content=text,
    )


def make_context(*entities: EntityRef) -> DrawingContext:
    return DrawingContext(file_path="test.dxf", entities=list(entities))


def make_move_op(handle: str, dx: float = 10.0, dy: float = 0.0) -> EditOperation:
    return EditOperation(
        op_type=OpType.MOVE_ENTITY,
        target_handle=handle,
        params={"dx": dx, "dy": dy},
    )


def make_delete_op(handle: str) -> EditOperation:
    return EditOperation(op_type=OpType.DELETE_ENTITY, target_handle=handle)


def make_edit_text_op(handle: str, new_text: str = "UPDATED") -> EditOperation:
    return EditOperation(
        op_type=OpType.EDIT_TEXT,
        target_handle=handle,
        params={"new_text": new_text},
    )


def make_add_block_op(block_name: str = "COL", x: float = 50.0, y: float = 50.0) -> EditOperation:
    return EditOperation(
        op_type=OpType.ADD_BLOCK,
        target_layer="STRUCTURAL",
        params={"block_name": block_name, "insert_point": {"x": x, "y": y}},
    )


# ---------------------------------------------------------------------------
# parse_precision_controls
# ---------------------------------------------------------------------------


class TestParsePrecisionControls:
    def test_none_metadata_returns_none(self):
        assert parse_precision_controls(None) is None

    def test_empty_dict_returns_none(self):
        assert parse_precision_controls({}) is None

    def test_missing_precision_key_returns_none(self):
        assert parse_precision_controls({"other": "value"}) is None

    def test_non_dict_precision_value_returns_none(self):
        assert parse_precision_controls({"precision": "not_a_dict"}) is None

    def test_null_precision_value_returns_none(self):
        assert parse_precision_controls({"precision": None}) is None

    def test_valid_precision_data_parsed(self):
        controls = parse_precision_controls(
            {
                "precision": {
                    "target_handles": ["A1"],
                    "confidence_threshold": 0.8,
                }
            }
        )
        assert controls is not None
        assert controls.target_handles == ["A1"]
        assert controls.confidence_threshold == 0.8

    def test_empty_precision_dict_returns_none(self):
        # An empty dict is falsy — treated as "no controls specified"
        controls = parse_precision_controls({"precision": {}})
        assert controls is None


# ---------------------------------------------------------------------------
# apply_entity_filter
# ---------------------------------------------------------------------------


class TestApplyEntityFilter:
    def test_empty_controls_passthrough(self):
        entities = [make_entity("A1"), make_entity("B2", layer="NOTES")]
        controls = PrecisionControls()
        result = apply_entity_filter(entities, controls)
        assert len(result) == 2

    def test_target_handles_filters(self):
        entities = [make_entity("A1"), make_entity("B2"), make_entity("C3")]
        controls = PrecisionControls(target_handles=["A1", "C3"])
        result = apply_entity_filter(entities, controls)
        assert [e.handle for e in result] == ["A1", "C3"]

    def test_target_handles_empty_list_passthrough(self):
        entities = [make_entity("A1"), make_entity("B2")]
        controls = PrecisionControls(target_handles=[])
        result = apply_entity_filter(entities, controls)
        assert len(result) == 2

    def test_target_layers_filters(self):
        entities = [
            make_entity("A1", layer="WALLS"),
            make_entity("B2", layer="NOTES"),
            make_entity("C3", layer="WALLS"),
        ]
        controls = PrecisionControls(target_layers=["WALLS"])
        result = apply_entity_filter(entities, controls)
        assert all(e.layer == "WALLS" for e in result)
        assert len(result) == 2

    def test_target_layers_case_insensitive(self):
        entities = [make_entity("A1", layer="WALLS"), make_entity("B2", layer="notes")]
        controls = PrecisionControls(target_layers=["walls"])
        result = apply_entity_filter(entities, controls)
        # Both should match (WALLS vs walls is case-insensitive in filter)
        assert make_entity("A1", layer="WALLS") in result

    def test_exclude_layers_removes(self):
        entities = [
            make_entity("A1", layer="WALLS"),
            make_entity("B2", layer="REVISION"),
            make_entity("C3", layer="NOTES"),
        ]
        controls = PrecisionControls(exclude_layers=["REVISION"])
        result = apply_entity_filter(entities, controls)
        assert all(e.layer != "REVISION" for e in result)
        assert len(result) == 2

    def test_exclude_layers_case_insensitive(self):
        entities = [make_entity("A1", layer="REVISION"), make_entity("B2", layer="WALLS")]
        controls = PrecisionControls(exclude_layers=["revision"])
        result = apply_entity_filter(entities, controls)
        assert len(result) == 1
        assert result[0].handle == "B2"

    def test_target_types_filters(self):
        entities = [
            make_entity("A1", entity_type=EntityType.LINE),
            make_entity("B2", entity_type=EntityType.TEXT),
            make_entity("C3", entity_type=EntityType.LINE),
        ]
        controls = PrecisionControls(target_types=["LINE"])
        result = apply_entity_filter(entities, controls)
        assert all(e.entity_type == EntityType.LINE for e in result)
        assert len(result) == 2

    def test_target_types_case_insensitive(self):
        entities = [make_entity("A1", entity_type=EntityType.TEXT)]
        controls = PrecisionControls(target_types=["text"])
        result = apply_entity_filter(entities, controls)
        assert len(result) == 1

    def test_model_space_only_filters(self):
        entities = [
            make_entity("A1", space="Model"),
            make_entity("B2", space="Sheet1"),
            make_entity("C3", space="Model"),
        ]
        controls = PrecisionControls(model_space_only=True)
        result = apply_entity_filter(entities, controls)
        assert all(e.space == "Model" for e in result)
        assert len(result) == 2

    def test_model_space_only_false_passthrough(self):
        entities = [make_entity("A1", space="Model"), make_entity("B2", space="Paper")]
        controls = PrecisionControls(model_space_only=False)
        result = apply_entity_filter(entities, controls)
        assert len(result) == 2

    def test_chained_filters_reduce_set(self):
        entities = [
            make_entity("A1", entity_type=EntityType.LINE, layer="WALLS", space="Model"),
            make_entity("B2", entity_type=EntityType.TEXT, layer="WALLS", space="Model"),
            make_entity("C3", entity_type=EntityType.LINE, layer="NOTES", space="Model"),
            make_entity("D4", entity_type=EntityType.LINE, layer="WALLS", space="Sheet1"),
        ]
        controls = PrecisionControls(
            target_layers=["WALLS"],
            target_types=["LINE"],
            model_space_only=True,
        )
        result = apply_entity_filter(entities, controls)
        assert len(result) == 1
        assert result[0].handle == "A1"

    def test_empty_entity_list(self):
        controls = PrecisionControls(target_handles=["A1"])
        result = apply_entity_filter([], controls)
        assert result == []


# ---------------------------------------------------------------------------
# apply_exact_delta
# ---------------------------------------------------------------------------


class TestApplyExactDelta:
    def test_move_op_dx_overridden(self):
        op = make_move_op("A1", dx=5.0, dy=0.0)
        result = apply_exact_delta([op], {"dx": 99.0})
        assert result[0].params["dx"] == 99.0
        assert result[0].params["dy"] == 0.0

    def test_move_op_dy_overridden(self):
        op = make_move_op("A1", dx=0.0, dy=5.0)
        result = apply_exact_delta([op], {"dy": -10.0})
        assert result[0].params["dy"] == -10.0
        assert result[0].params["dx"] == 0.0

    def test_move_op_both_overridden(self):
        op = make_move_op("A1", dx=1.0, dy=1.0)
        result = apply_exact_delta([op], {"dx": 20.0, "dy": 30.0})
        assert result[0].params["dx"] == 20.0
        assert result[0].params["dy"] == 30.0

    def test_non_move_op_unchanged(self):
        op = make_delete_op("B2")
        result = apply_exact_delta([op], {"dx": 99.0, "dy": 99.0})
        assert result[0].op_type == OpType.DELETE_ENTITY

    def test_edit_text_op_unchanged(self):
        op = make_edit_text_op("C3", new_text="HELLO")
        result = apply_exact_delta([op], {"dx": 5.0})
        assert result[0].params.get("new_text") == "HELLO"

    def test_mixed_ops_selective_override(self):
        ops = [make_move_op("A1", dx=1.0), make_delete_op("B2"), make_move_op("C3", dx=2.0)]
        result = apply_exact_delta(ops, {"dx": 50.0})
        assert result[0].params["dx"] == 50.0
        assert result[1].op_type == OpType.DELETE_ENTITY
        assert result[2].params["dx"] == 50.0

    def test_does_not_mutate_original(self):
        op = make_move_op("A1", dx=5.0, dy=3.0)
        original_params = dict(op.params)
        apply_exact_delta([op], {"dx": 99.0})
        assert op.params["dx"] == original_params["dx"]  # original unchanged

    def test_partial_delta_only_dx(self):
        op = make_move_op("A1", dx=1.0, dy=2.0)
        result = apply_exact_delta([op], {"dx": 10.0})
        assert result[0].params["dx"] == 10.0
        assert result[0].params["dy"] == 2.0  # dy unchanged

    def test_empty_delta_passthrough(self):
        op = make_move_op("A1", dx=5.0, dy=3.0)
        result = apply_exact_delta([op], {})
        assert result[0].params["dx"] == 5.0
        assert result[0].params["dy"] == 3.0


# ---------------------------------------------------------------------------
# check_confidence_threshold
# ---------------------------------------------------------------------------


class TestCheckConfidenceThreshold:
    def test_meets_threshold(self):
        assert check_confidence_threshold(0.8, 0.5) is True

    def test_below_threshold(self):
        assert check_confidence_threshold(0.3, 0.5) is False

    def test_equal_threshold(self):
        assert check_confidence_threshold(0.5, 0.5) is True

    def test_zero_threshold_always_passes(self):
        assert check_confidence_threshold(0.0, 0.0) is True

    def test_one_threshold_requires_perfect(self):
        assert check_confidence_threshold(0.99, 1.0) is False
        assert check_confidence_threshold(1.0, 1.0) is True


# ---------------------------------------------------------------------------
# build_match_candidates
# ---------------------------------------------------------------------------


class TestBuildMatchCandidates:
    def test_empty_entities_returns_empty(self):
        controls = PrecisionControls(target_layers=["WALLS"])
        result = build_match_candidates([], controls)
        assert result == []

    def test_exact_handle_gets_highest_score(self):
        entities = [
            make_entity("A1", layer="WALLS"),
            make_entity("B2", layer="WALLS"),
        ]
        controls = PrecisionControls(target_handles=["A1"])
        result = build_match_candidates(entities, controls)
        assert result[0].handle == "A1"
        assert result[0].confidence > result[1].confidence

    def test_max_candidates_respected(self):
        entities = [make_entity(f"H{i}") for i in range(20)]
        controls = PrecisionControls()
        result = build_match_candidates(entities, controls, max_candidates=5)
        assert len(result) <= 5

    def test_layer_match_scores_higher_than_default(self):
        entities = [
            make_entity("A1", layer="WALLS"),
            make_entity("B2", layer="OTHER"),
        ]
        controls = PrecisionControls(target_layers=["WALLS"])
        result = build_match_candidates(entities, controls)
        # A1 should score higher due to layer match
        handles = [c.handle for c in result]
        assert handles[0] == "A1"

    def test_type_match_boosts_score(self):
        entities = [
            make_entity("A1", entity_type=EntityType.LINE),
            make_entity("B2", entity_type=EntityType.TEXT),
        ]
        controls = PrecisionControls(target_types=["LINE"])
        result = build_match_candidates(entities, controls)
        assert result[0].handle == "A1"

    def test_location_populated_from_insert_point(self):
        entity = make_entity("A1", x=10.0, y=20.0)
        controls = PrecisionControls()
        result = build_match_candidates([entity], controls)
        assert result[0].location == (10.0, 20.0)

    def test_no_insert_point_location_is_none(self):
        entity = make_entity("A1")  # no x/y
        controls = PrecisionControls()
        result = build_match_candidates([entity], controls)
        assert result[0].location is None

    def test_match_reason_populated(self):
        entity = make_entity("A1", layer="WALLS")
        controls = PrecisionControls(target_layers=["WALLS"])
        result = build_match_candidates([entity], controls)
        assert "layer=" in result[0].match_reason

    def test_confidence_capped_at_one(self):
        entity = make_entity("A1", layer="WALLS")
        controls = PrecisionControls(target_handles=["A1"], target_layers=["WALLS"])
        result = build_match_candidates([entity], controls)
        assert result[0].confidence <= 1.0


# ---------------------------------------------------------------------------
# build_action_details
# ---------------------------------------------------------------------------


class TestBuildActionDetails:
    def test_basic_move_op(self):
        entity = make_entity("A1", layer="WALLS", x=10.0, y=20.0)
        context = make_context(entity)
        changeset = ChangeSet(prompt="move", operations=[make_move_op("A1", dx=5.0, dy=0.0)])
        details = build_action_details(changeset, context)
        assert len(details) == 1
        d = details[0]
        assert d.entity_handle == "A1"
        assert d.action == "move_entity"
        assert d.before["x"] == 10.0
        assert d.after["x"] == 15.0
        assert d.status == ActionStatus.PLANNED

    def test_move_op_no_entity_uses_delta(self):
        context = make_context()  # no entities
        changeset = ChangeSet(prompt="move", operations=[make_move_op("MISSING", dx=5.0, dy=3.0)])
        details = build_action_details(changeset, context)
        assert details[0].after["dx"] == 5.0
        assert details[0].after["dy"] == 3.0

    def test_edit_text_op_before_after(self):
        entity = make_entity("B2", entity_type=EntityType.TEXT, layer="NOTES", text="OLD TEXT")
        context = make_context(entity)
        changeset = ChangeSet(
            prompt="edit", operations=[make_edit_text_op("B2", new_text="NEW TEXT")]
        )
        details = build_action_details(changeset, context)
        assert details[0].before["text"] == "OLD TEXT"
        assert details[0].after["text"] == "NEW TEXT"

    def test_add_block_op_after_state(self):
        context = make_context()
        changeset = ChangeSet(
            prompt="add", operations=[make_add_block_op("COL_MARK", x=10.0, y=20.0)]
        )
        details = build_action_details(changeset, context)
        assert details[0].after["block_name"] == "COL_MARK"
        assert details[0].after["x"] == 10.0
        assert details[0].after["y"] == 20.0

    def test_delete_op_action(self):
        entity = make_entity("C3", layer="STRUCTURAL")
        context = make_context(entity)
        changeset = ChangeSet(prompt="del", operations=[make_delete_op("C3")])
        details = build_action_details(changeset, context)
        assert details[0].action == "delete_entity"

    def test_entity_evidence_populated(self):
        entity = make_entity("A1", layer="WALLS", text="Some text")
        context = make_context(entity)
        changeset = ChangeSet(prompt="test", operations=[make_move_op("A1")])
        details = build_action_details(changeset, context)
        assert any("layer" in ev for ev in details[0].evidence)
        assert any("text" in ev for ev in details[0].evidence)

    def test_unknown_entity_handle_uses_target_layer(self):
        context = make_context()
        op = EditOperation(
            op_type=OpType.ADD_BLOCK,
            target_layer="STRUCTURAL",
            params={"block_name": "B", "insert_point": {"x": 0, "y": 0}},
        )
        changeset = ChangeSet(prompt="add", operations=[op])
        details = build_action_details(changeset, context)
        assert details[0].layer == "STRUCTURAL"

    def test_blocked_status_from_validation(self):
        entity = make_entity("A1", layer="TITLE")
        context = make_context(entity)
        changeset = ChangeSet(prompt="move protected", operations=[make_move_op("A1")])

        # Mock a validation object with a blocker mentioning handle A1
        class FakeBlocker:
            message = "Cannot edit entity A1 on protected layer"

        class FakeValidation:
            blockers = [FakeBlocker()]
            warnings = []

        details = build_action_details(changeset, context, FakeValidation())
        assert details[0].status == ActionStatus.BLOCKED

    def test_planned_status_when_no_blockers(self):
        entity = make_entity("A1", layer="WALLS")
        context = make_context(entity)
        changeset = ChangeSet(prompt="move", operations=[make_move_op("A1")])

        class FakeValidation:
            blockers = []
            warnings = []

        details = build_action_details(changeset, context, FakeValidation())
        assert details[0].status == ActionStatus.PLANNED

    def test_multiple_ops_in_changeset(self):
        e1 = make_entity("A1", layer="WALLS")
        e2 = make_entity("B2", entity_type=EntityType.TEXT, layer="NOTES", text="OLD")
        context = make_context(e1, e2)
        changeset = ChangeSet(
            prompt="multi",
            operations=[make_move_op("A1"), make_edit_text_op("B2", new_text="NEW")],
        )
        details = build_action_details(changeset, context)
        assert len(details) == 2
        assert details[0].action == "move_entity"
        assert details[1].action == "edit_text"
