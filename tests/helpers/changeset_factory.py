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


# --- V2 transform builders ---


def make_rotate(
    handle: str,
    *,
    angle: float = 90.0,
    cx: float = 0,
    cy: float = 0,
    prompt: str = "Rotate entity",
) -> ChangeSet:
    """Build a ChangeSet with a single rotate operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ROTATE_ENTITY,
                target_handle=handle,
                params={"angle": angle, "cx": cx, "cy": cy},
            )
        ],
    )


def make_copy(
    handle: str,
    *,
    dx: float = 30.0,
    dy: float = 0.0,
    prompt: str = "Copy entity",
) -> ChangeSet:
    """Build a ChangeSet with a single copy operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.COPY_ENTITY,
                target_handle=handle,
                params={"dx": dx, "dy": dy},
            )
        ],
    )


def make_scale(
    handle: str,
    *,
    factor: float = 2.0,
    cx: float = 0,
    cy: float = 0,
    prompt: str = "Scale entity",
) -> ChangeSet:
    """Build a ChangeSet with a single scale operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.SCALE_ENTITY,
                target_handle=handle,
                params={"factor": factor, "cx": cx, "cy": cy},
            )
        ],
    )


def make_mirror(
    handle: str,
    *,
    axis: str = "x",
    value: float = 0,
    prompt: str = "Mirror entity",
) -> ChangeSet:
    """Build a ChangeSet with a single mirror operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.MIRROR_ENTITY,
                target_handle=handle,
                params={"axis": axis, "value": value},
            )
        ],
    )


# --- V2 creation builders ---


def make_add_line(
    start_x: float = 0,
    start_y: float = 0,
    end_x: float = 100,
    end_y: float = 0,
    *,
    layer: str | None = None,
    prompt: str = "Add line",
) -> ChangeSet:
    """Build a ChangeSet with a single add_line operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_LINE,
                target_layer=layer,
                params={
                    "start": {"x": start_x, "y": start_y},
                    "end": {"x": end_x, "y": end_y},
                    "layer": layer,
                },
            )
        ],
    )


def make_add_polyline(
    points: list[dict] | None = None,
    *,
    closed: bool = False,
    layer: str | None = None,
    prompt: str = "Add polyline",
) -> ChangeSet:
    """Build a ChangeSet with a single add_polyline operation."""
    if points is None:
        points = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}, {"x": 0, "y": 50}]
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_POLYLINE,
                target_layer=layer,
                params={
                    "points": points,
                    "closed": closed,
                    "layer": layer,
                },
            )
        ],
    )


def make_add_circle(
    cx: float = 50,
    cy: float = 50,
    radius: float = 10,
    *,
    layer: str | None = None,
    prompt: str = "Add circle",
) -> ChangeSet:
    """Build a ChangeSet with a single add_circle operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_CIRCLE,
                target_layer=layer,
                params={
                    "center": {"x": cx, "y": cy},
                    "radius": radius,
                    "layer": layer,
                },
            )
        ],
    )


def make_add_arc(
    cx: float = 50,
    cy: float = 50,
    radius: float = 10,
    *,
    start_angle: float = 0,
    end_angle: float = 90,
    layer: str | None = None,
    prompt: str = "Add arc",
) -> ChangeSet:
    """Build a ChangeSet with a single add_arc operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_ARC,
                target_layer=layer,
                params={
                    "center": {"x": cx, "y": cy},
                    "radius": radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                    "layer": layer,
                },
            )
        ],
    )


def make_add_text(
    text: str = "NEW ANNOTATION",
    x: float = 10,
    y: float = 10,
    *,
    height: float = 2.5,
    layer: str | None = None,
    prompt: str = "Add text",
) -> ChangeSet:
    """Build a ChangeSet with a single add_text operation."""
    return ChangeSet(
        prompt=prompt,
        operations=[
            EditOperation(
                op_type=OpType.ADD_TEXT,
                target_layer=layer,
                params={
                    "text": text,
                    "insert": {"x": x, "y": y},
                    "height": height,
                    "layer": layer,
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
