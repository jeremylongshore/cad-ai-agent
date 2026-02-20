"""Preview model — builds a preview summary of proposed changes before apply."""

from __future__ import annotations

from ..models.cad_schema import DrawingContext
from ..models.changes_schema import ValidationResult
from ..models.ops_schema import ChangeSet, OpType
from .entity_index import EntityIndex


class PreviewItem:
    """A single preview item describing what an operation will do."""

    def __init__(self, index: int, description: str, entity_handle: str | None = None):
        self.index = index
        self.description = description
        self.entity_handle = entity_handle

    def __str__(self) -> str:
        return f"[{self.index}] {self.description}"


class PreviewModel:
    """Builds human-readable preview of a changeset before apply."""

    def __init__(
        self,
        changeset: ChangeSet,
        context: DrawingContext,
        validation: ValidationResult,
    ):
        self.changeset = changeset
        self.context = context
        self.validation = validation
        self._items: list[PreviewItem] = []
        self._build()

    def _build(self) -> None:
        entity_index = EntityIndex(self.context)

        for i, op in enumerate(self.changeset.operations):
            entity = (
                entity_index.get_by_handle(op.target_handle)
                if op.target_handle
                else None
            )
            desc = self._describe_op(op, entity)
            self._items.append(PreviewItem(i, desc, op.target_handle))

    def _describe_op(self, op, entity) -> str:
        entity_label = ""
        if entity:
            entity_label = f" [{entity.entity_type.value} on {entity.layer}]"

        if op.op_type == OpType.MOVE_ENTITY:
            dx = op.params.get("dx", 0)
            dy = op.params.get("dy", 0)
            return f"Move{entity_label} by ({dx}, {dy})"
        elif op.op_type == OpType.EDIT_TEXT:
            new_text = op.params.get("new_text", "")
            return f"Edit text{entity_label} → {new_text!r}"
        elif op.op_type == OpType.DELETE_ENTITY:
            return f"Delete{entity_label}"
        elif op.op_type == OpType.ADD_BLOCK:
            block = op.params.get("block_name", "?")
            pt = op.params.get("insert_point", {})
            return f"Add block {block} at ({pt.get('x', 0)}, {pt.get('y', 0)})"
        return f"Unknown op: {op.op_type}"

    @property
    def items(self) -> list[PreviewItem]:
        return list(self._items)

    @property
    def is_valid(self) -> bool:
        return self.validation.valid

    @property
    def summary(self) -> str:
        lines = [f"Preview: {len(self._items)} operation(s)"]
        if not self.validation.valid:
            lines.append(f"  BLOCKED: {len(self.validation.blockers)} blocker(s)")
        for item in self._items:
            lines.append(f"  {item}")
        return "\n".join(lines)
