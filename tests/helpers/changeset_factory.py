"""ChangeSet factory — one-liner test data builders for operations.

Each builder returns a ready-to-validate ChangeSet with sensible defaults.
"""

from __future__ import annotations

from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


def make_move(
    handle: str,
    *,
    dx: float = 24.0,
    dy: float = 0.0,
    prompt: str = "Move entity",
) -> ChangeSet:
    """Build a ChangeSet with a single move operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.MOVE_ENTITY,
                target_handle=handle,
                params={"dx": dx, "dy": dy},
            )
        ],
    )


def make_delete(
    handle: str,
    *,
    prompt: str = "Delete entity",
) -> ChangeSet:
    """Build a ChangeSet with a single delete operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.DELETE_ENTITY,
                target_handle=handle,
            )
        ],
    )


def make_edit_text(
    handle: str,
    new_text: str = "UPDATED TEXT",
    *,
    prompt: str = "Edit text",
) -> ChangeSet:
    """Build a ChangeSet with a single edit_text operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.EDIT_TEXT,
                target_handle=handle,
                params={"new_text": new_text},
            )
        ],
    )


def make_add_block(
    block_name: str = "COLUMN_MARK",
    x: float = 50.0,
    y: float = 50.0,
    *,
    layer: str | None = None,
    prompt: str = "Add block",
) -> ChangeSet:
    """Build a ChangeSet with a single add_block operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_BLOCK,
                target_layer=layer,
                params={
                    "block_name": block_name,
                    "insert_point": {"x": x, "y": y},
                },
            )
        ],
    )


def make_multi_op(
    *operations: EditOperation,
    prompt: str = "Multi-op changeset",
) -> ChangeSet:
    """Build a ChangeSet from multiple EditOperation objects."""
    return ChangeSet(prompt=prompt, operations=list(operations))
