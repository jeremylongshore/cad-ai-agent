"""Operation schemas: structured edit operations for DXF editing."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OpType(StrEnum):
    """Allowed operation types."""

    # V1 operations
    MOVE_ENTITY = "move_entity"
    EDIT_TEXT = "edit_text"
    DELETE_ENTITY = "delete_entity"
    ADD_BLOCK = "add_block"

    # V2 transform operations
    ROTATE_ENTITY = "rotate_entity"
    COPY_ENTITY = "copy_entity"
    SCALE_ENTITY = "scale_entity"
    MIRROR_ENTITY = "mirror_entity"

    # V2 entity creation operations
    ADD_LINE = "add_line"
    ADD_POLYLINE = "add_polyline"
    ADD_CIRCLE = "add_circle"
    ADD_ARC = "add_arc"
    ADD_TEXT = "add_text"


class EditOperation(BaseModel):
    """A single structured edit operation returned by the planner."""

    op_type: OpType
    target_handle: str | None = Field(
        default=None,
        description="Handle of the target entity (required for move/edit/delete)",
    )
    target_layer: str | None = None
    target_space: str = Field(
        default="Model",
        description="Space/layout name: 'Model' or a paper space layout name",
    )
    params: dict[str, Any] = Field(default_factory=dict)

    # move_entity params: dx, dy
    # edit_text params: new_text
    # delete_entity params: (none)
    # add_block params: block_name, insert_point (x, y), scale, rotation
    # rotate_entity params: angle (degrees), cx, cy (rotation center, optional)
    # copy_entity params: dx, dy (offset for the copy)
    # scale_entity params: factor, cx, cy (scale center, optional)
    # mirror_entity params: axis ("x" or "y"), value (coordinate of mirror line)
    # add_line params: start (x, y), end (x, y), layer
    # add_polyline params: points [(x, y), ...], closed (bool), layer
    # add_circle params: center (x, y), radius, layer
    # add_arc params: center (x, y), radius, start_angle, end_angle, layer
    # add_text params: text, insert (x, y), height, layer, rotation (optional)


class ChangeSet(BaseModel):
    """A set of operations to apply as a batch."""

    model_config = {"arbitrary_types_allowed": True}

    operations: list[EditOperation] = Field(default_factory=list)
    prompt: str = ""
    revision_label: str | None = None
    message: str | None = Field(
        default=None,
        description="Optional message from the LLM (e.g. explanation when no ops are returned)",
    )
    planner_trace: Any = Field(default=None, exclude=True)

    @property
    def op_count(self) -> int:
        return len(self.operations)


class AppliedChange(BaseModel):
    """Record of a successfully applied operation."""

    operation: EditOperation
    success: bool = True
    entity_handle: str | None = None
    description: str = ""
