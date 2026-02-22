"""Operation schemas: structured edit operations for DXF editing."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OpType(StrEnum):
    """Allowed V1 operation types."""

    MOVE_ENTITY = "move_entity"
    EDIT_TEXT = "edit_text"
    DELETE_ENTITY = "delete_entity"
    ADD_BLOCK = "add_block"


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


class ChangeSet(BaseModel):
    """A set of operations to apply as a batch."""

    operations: list[EditOperation] = Field(default_factory=list)
    prompt: str = ""
    revision_label: str | None = None

    @property
    def op_count(self) -> int:
        return len(self.operations)


class AppliedChange(BaseModel):
    """Record of a successfully applied operation."""

    operation: EditOperation
    success: bool = True
    entity_handle: str | None = None
    description: str = ""
