"""Plan converter — bridges EditPlan (EPIC-07) to legacy ChangeSet.

Converts typed EditAction objects into EditOperation objects that the
existing EditEngine can apply. Preserves action order and returns an
index map for correlating results back to actions.
"""

from __future__ import annotations

from ..models.cad_schema import DrawingContext
from ..models.ops_schema import ChangeSet, EditOperation, OpType
from ..models.plan_schema import EditAction, EditActionType, EditPlan, PlanValidationStatus

_ACTION_TO_OP: dict[EditActionType, OpType] = {
    EditActionType.MOVE_ENTITY: OpType.MOVE_ENTITY,
    EditActionType.EDIT_TEXT: OpType.EDIT_TEXT,
    EditActionType.DELETE_ENTITY: OpType.DELETE_ENTITY,
    EditActionType.ADD_BLOCK: OpType.ADD_BLOCK,
    EditActionType.REPLICATE_NOTE: OpType.ADD_BLOCK,
}


def plan_to_changeset(
    plan: EditPlan,
    context: DrawingContext | None = None,
) -> tuple[ChangeSet, dict[int, int]]:
    """Convert an EditPlan into a ChangeSet for the legacy EditEngine.

    Returns (changeset, action_index_map) where action_index_map maps
    changeset operation index → plan action index.

    Blocked actions are skipped. REPLICATE_NOTE is converted to ADD_BLOCK
    by looking up the source entity's block_name via context.
    """
    operations: list[EditOperation] = []
    action_index_map: dict[int, int] = {}

    for action_idx, action in enumerate(plan.actions):
        if action.validation.status == PlanValidationStatus.BLOCKED:
            continue

        op = _convert_action(action, context)
        if op is not None:
            op_idx = len(operations)
            operations.append(op)
            action_index_map[op_idx] = action_idx

    changeset = ChangeSet(
        operations=operations,
        prompt=plan.prompt,
    )
    return changeset, action_index_map


def _convert_action(
    action: EditAction,
    context: DrawingContext | None,
) -> EditOperation | None:
    """Convert a single EditAction to an EditOperation."""
    op_type = _ACTION_TO_OP.get(action.action_type)
    if op_type is None:
        return None

    params = dict(action.params)

    if action.action_type == EditActionType.REPLICATE_NOTE:
        params = _build_replicate_params(action, context)

    return EditOperation(
        op_type=op_type,
        target_handle=action.target_handle,
        target_layer=action.target_layer,
        params=params,
    )


def _build_replicate_params(
    action: EditAction,
    context: DrawingContext | None,
) -> dict:
    """Build ADD_BLOCK params from a REPLICATE_NOTE action."""
    params: dict = {}

    # Get block_name from source entity via context
    source_handles = action.params.get("source_handles", [])
    block_name = action.params.get("block_name", "")

    if not block_name and context and source_handles:
        for handle in source_handles:
            entity = context.get_entity_by_handle(handle)
            if entity and entity.block_name:
                block_name = entity.block_name
                break

    params["block_name"] = block_name
    params["insert_point"] = action.params.get("target_centroid", {"x": 0, "y": 0})

    return params
