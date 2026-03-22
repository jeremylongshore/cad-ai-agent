"""Preview model — builds a preview summary of proposed changes before apply."""

from __future__ import annotations

from ..models.cad_schema import DrawingContext
from ..models.changes_schema import ValidationResult
from ..models.ops_schema import ChangeSet, OpType


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
        entity_index = self.context.index

        for i, op in enumerate(self.changeset.operations):
            entity = entity_index.get_by_handle(op.target_handle) if op.target_handle else None
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
            return f"Edit text{entity_label} \u2192 {new_text!r}"
        elif op.op_type == OpType.DELETE_ENTITY:
            return f"Delete{entity_label}"
        elif op.op_type == OpType.ADD_BLOCK:
            block = op.params.get("block_name", "?")
            pt = op.params.get("insert_point", {})
            return f"Add block {block} at ({pt.get('x', 0)}, {pt.get('y', 0)})"
        elif op.op_type == OpType.ROTATE_ENTITY:
            angle = op.params.get("angle", 0)
            return f"Rotate{entity_label} by {angle}\u00b0"
        elif op.op_type == OpType.COPY_ENTITY:
            dx = op.params.get("dx", 0)
            dy = op.params.get("dy", 0)
            return f"Copy{entity_label} with offset ({dx}, {dy})"
        elif op.op_type == OpType.SCALE_ENTITY:
            factor = op.params.get("factor", 1.0)
            return f"Scale{entity_label} by {factor}x"
        elif op.op_type == OpType.MIRROR_ENTITY:
            axis = op.params.get("axis", "x")
            value = op.params.get("value", 0)
            return f"Mirror{entity_label} across {axis}={value}"
        elif op.op_type == OpType.ADD_LINE:
            start = op.params.get("start", {})
            end = op.params.get("end", {})
            return (
                f"Add line from ({start.get('x', 0)}, {start.get('y', 0)}) "
                f"to ({end.get('x', 0)}, {end.get('y', 0)})"
            )
        elif op.op_type == OpType.ADD_POLYLINE:
            pts = op.params.get("points", [])
            closed = op.params.get("closed", False)
            return f"Add {'closed ' if closed else ''}polyline with {len(pts)} points"
        elif op.op_type == OpType.ADD_CIRCLE:
            c = op.params.get("center", {})
            r = op.params.get("radius", 0)
            return f"Add circle at ({c.get('x', 0)}, {c.get('y', 0)}) r={r}"
        elif op.op_type == OpType.ADD_ARC:
            c = op.params.get("center", {})
            r = op.params.get("radius", 0)
            sa = op.params.get("start_angle", 0)
            ea = op.params.get("end_angle", 0)
            return f"Add arc at ({c.get('x', 0)}, {c.get('y', 0)}) r={r} {sa}\u00b0-{ea}\u00b0"
        elif op.op_type == OpType.ADD_TEXT:
            text = op.params.get("text", "")
            ins = op.params.get("insert", {})
            return f"Add text {text!r} at ({ins.get('x', 0)}, {ins.get('y', 0)})"
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
