"""Edit engine — applies validated operations to a DXF document in memory."""

from __future__ import annotations

import logging
from pathlib import Path

import ezdxf

from ..models.ops_schema import AppliedChange, ChangeSet, EditOperation, OpType

logger = logging.getLogger(__name__)


class EditEngine:
    """Applies structured operations to a DXF document.

    Operates on a working copy — never modifies the original file.
    """

    def __init__(self, dxf_path: str | Path) -> None:
        self.dxf_path = Path(dxf_path)
        self.doc = ezdxf.readfile(str(self.dxf_path))
        self.msp = self.doc.modelspace()
        self._applied: list[AppliedChange] = []

    def apply_changeset(self, changeset: ChangeSet) -> list[AppliedChange]:
        """Apply all operations in a validated changeset.

        Returns list of AppliedChange records.
        """
        results = []
        for op in changeset.operations:
            result = self._apply_operation(op)
            results.append(result)
            self._applied.append(result)
        return results

    def save(self, output_path: str | Path) -> Path:
        """Save the modified document to a new path."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.saveas(str(output_path))
        logger.info("Saved edited DXF to: %s", output_path)
        return output_path

    @property
    def applied_changes(self) -> list[AppliedChange]:
        return list(self._applied)

    def _apply_operation(self, op: EditOperation) -> AppliedChange:
        """Apply a single operation. Assumes validation has already passed."""
        if op.op_type == OpType.MOVE_ENTITY:
            return self._apply_move(op)
        elif op.op_type == OpType.EDIT_TEXT:
            return self._apply_edit_text(op)
        elif op.op_type == OpType.DELETE_ENTITY:
            return self._apply_delete(op)
        elif op.op_type == OpType.ADD_BLOCK:
            return self._apply_add_block(op)
        else:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Unknown op type: {op.op_type}",
            )

    def _find_entity(self, handle: str):
        """Find entity by handle in model space."""
        return self.doc.entitydb.get(handle)

    def _apply_move(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(
                operation=op, success=False, description="Entity not found"
            )

        dx = op.params.get("dx", 0)
        dy = op.params.get("dy", 0)

        try:
            entity.translate(dx, dy, 0)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Moved entity {op.target_handle} by ({dx}, {dy})",
            )
        except Exception as e:
            return AppliedChange(
                operation=op, success=False, description=f"Move failed: {e}"
            )

    def _apply_edit_text(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(
                operation=op, success=False, description="Entity not found"
            )

        new_text = op.params.get("new_text", "")
        dxf_type = entity.dxftype()

        try:
            if dxf_type == "TEXT":
                entity.dxf.text = new_text
            elif dxf_type == "MTEXT":
                entity.text = new_text
            else:
                return AppliedChange(
                    operation=op,
                    success=False,
                    description=f"Cannot edit text on entity type: {dxf_type}",
                )

            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Updated text on {op.target_handle} to: {new_text!r}",
            )
        except Exception as e:
            return AppliedChange(
                operation=op, success=False, description=f"Edit text failed: {e}"
            )

    def _apply_delete(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(
                operation=op, success=False, description="Entity not found"
            )

        try:
            self.msp.delete_entity(entity)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Deleted entity {op.target_handle}",
            )
        except Exception as e:
            return AppliedChange(
                operation=op, success=False, description=f"Delete failed: {e}"
            )

    def _apply_add_block(self, op: EditOperation) -> AppliedChange:
        block_name: str = op.params.get("block_name", "")
        insert_point = op.params.get("insert_point", {})
        x = insert_point.get("x", 0)
        y = insert_point.get("y", 0)
        scale = op.params.get("scale", 1.0)
        rotation = op.params.get("rotation", 0.0)

        try:
            if not block_name or block_name not in self.doc.blocks:
                return AppliedChange(
                    operation=op,
                    success=False,
                    description=f"Block definition not found: {block_name}",
                )

            attribs = {}
            if op.target_layer:
                attribs["layer"] = op.target_layer

            ref = self.msp.add_blockref(
                block_name,
                insert=(x, y),
                dxfattribs={
                    "xscale": scale,
                    "yscale": scale,
                    "rotation": rotation,
                    **attribs,
                },
            )
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=ref.dxf.handle,
                description=f"Inserted block {block_name} at ({x}, {y})",
            )
        except Exception as e:
            return AppliedChange(
                operation=op, success=False, description=f"Add block failed: {e}"
            )
