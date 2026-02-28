"""RevisionApplier — applies approved RevisionOps to a master DXF document."""

from __future__ import annotations

import logging
import uuid

import ezdxf

from ...models.comparison_schema import (
    AppliedRevisionOp,
    ApplyResult,
    ApprovalSet,
    RevisionOp,
    RevisionOpType,
)

logger = logging.getLogger(__name__)

# Apply ordering: deterministic for handle safety
_OP_ORDER = {
    RevisionOpType.MODIFY_TEXT: 0,
    RevisionOpType.MODIFY_GEOMETRY: 1,
    RevisionOpType.MODIFY_ATTRIBUTES: 2,
    RevisionOpType.MOVE: 3,
    RevisionOpType.DELETE: 4,
    RevisionOpType.ADD: 5,
}


class RevisionApplier:
    """Applies approved RevisionOps to a master ezdxf document.

    Ordering: MODIFY → MOVE → DELETE → ADD (handle safety).
    """

    def __init__(self, master_doc: ezdxf.document.Drawing) -> None:
        self.doc = master_doc
        self.msp = master_doc.modelspace()

    def apply(
        self,
        ops: list[RevisionOp],
        approval_set: ApprovalSet,
        *,
        fail_fast: bool = False,
    ) -> ApplyResult:
        """Apply approved ops in safe order.

        Skips rejected/pending ops. Records each result.
        """
        run_id = uuid.uuid4().hex[:8]
        applied: list[AppliedRevisionOp] = []
        skipped = 0
        rejected = 0

        approved_ids = approval_set.approved_op_ids
        rejected_ids = approval_set.rejected_op_ids

        sorted_ops = sorted(ops, key=lambda o: _OP_ORDER.get(o.op_type, 99))

        for op in sorted_ops:
            if op.op_id in rejected_ids:
                rejected += 1
                continue
            if op.op_id not in approved_ids:
                skipped += 1
                continue

            result = self._apply_one(op)
            applied.append(result)

            if fail_fast and not result.success:
                break

        return ApplyResult(
            run_id=run_id,
            applied=applied,
            skipped_count=skipped,
            rejected_count=rejected,
        )

    def _apply_one(self, op: RevisionOp) -> AppliedRevisionOp:
        try:
            handler = {
                RevisionOpType.MOVE: self._apply_move,
                RevisionOpType.DELETE: self._apply_delete,
                RevisionOpType.ADD: self._apply_add,
                RevisionOpType.MODIFY_TEXT: self._apply_modify_text,
                RevisionOpType.MODIFY_GEOMETRY: self._apply_modify_geometry,
                RevisionOpType.MODIFY_ATTRIBUTES: self._apply_modify_attributes,
            }.get(op.op_type)

            if handler is None:
                return AppliedRevisionOp(
                    op_id=op.op_id,
                    op_type=op.op_type,
                    success=False,
                    error=f"Unknown op type: {op.op_type}",
                )
            return handler(op)
        except Exception as exc:
            logger.warning("Failed to apply op %s: %s", op.op_id, exc)
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=str(exc),
            )

    def _find_entity(self, handle: str):
        return self.doc.entitydb.get(handle)

    def _apply_move(self, op: RevisionOp) -> AppliedRevisionOp:
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Entity {op.target_handle} not found",
            )
        dx = op.forward.get("dx", 0)
        dy = op.forward.get("dy", 0)
        entity.translate(dx, dy, 0)
        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=op.target_handle,
            description=f"Moved by ({dx}, {dy})",
        )

    def _apply_delete(self, op: RevisionOp) -> AppliedRevisionOp:
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Entity {op.target_handle} not found",
            )
        self.msp.delete_entity(entity)
        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=op.target_handle,
            description=f"Deleted entity {op.target_handle}",
        )

    def _apply_add(self, op: RevisionOp) -> AppliedRevisionOp:
        snapshot = op.forward.get("snapshot", {})
        entity_type = snapshot.get("entity_type", "")
        layer = snapshot.get("layer", op.target_layer)
        points = snapshot.get("points", [])

        # Ensure layer exists
        if layer not in self.doc.layers:
            self.doc.layers.add(layer)

        new_entity: ezdxf.entities.DXFGraphic | None = None

        if entity_type == "LINE" and len(points) >= 2:
            start = (points[0]["x"], points[0]["y"])
            end = (points[1]["x"], points[1]["y"])
            new_entity = self.msp.add_line(start, end, dxfattribs={"layer": layer})
        elif entity_type == "LWPOLYLINE" and points:
            pts = [(p["x"], p["y"]) for p in points]
            new_entity = self.msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
        elif entity_type == "TEXT":
            text = snapshot.get("text_content", "")
            insert = (points[0]["x"], points[0]["y"]) if points else (0, 0)
            new_entity = self.msp.add_text(text, dxfattribs={"layer": layer, "insert": insert})
        elif entity_type == "MTEXT":
            text = snapshot.get("text_content", "")
            insert = (points[0]["x"], points[0]["y"]) if points else (0, 0)
            new_entity = self.msp.add_mtext(text, dxfattribs={"layer": layer, "insert": insert})
        elif entity_type == "INSERT":
            block_name = snapshot.get("block_name", "")
            if not block_name or block_name not in self.doc.blocks:
                return AppliedRevisionOp(
                    op_id=op.op_id,
                    op_type=op.op_type,
                    success=False,
                    error=f"Block definition not found: {block_name}",
                )
            insert = (points[0]["x"], points[0]["y"]) if points else (0, 0)
            attribs = snapshot.get("attributes", {})
            new_entity = self.msp.add_blockref(
                block_name,
                insert=insert,
                dxfattribs={
                    "layer": layer,
                    "xscale": attribs.get("xscale", 1.0),
                    "yscale": attribs.get("yscale", 1.0),
                    "rotation": attribs.get("rotation", 0.0),
                },
            )
        else:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Unsupported entity type for add: {entity_type}",
            )

        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=new_entity.dxf.handle,
            description=f"Added {entity_type} on {layer}",
        )

    def _apply_modify_text(self, op: RevisionOp) -> AppliedRevisionOp:
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Entity {op.target_handle} not found",
            )

        new_text = op.forward.get("new_text", "")
        dxf_type = entity.dxftype()

        if dxf_type == "TEXT":
            entity.dxf.text = new_text
        elif dxf_type == "MTEXT":
            entity.text = new_text
        else:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Cannot modify text on {dxf_type}",
            )

        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=op.target_handle,
            description=f"Text changed to {new_text!r}",
        )

    def _apply_modify_geometry(self, op: RevisionOp) -> AppliedRevisionOp:
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Entity {op.target_handle} not found",
            )

        new_points = op.forward.get("new_points", [])
        dxf_type = entity.dxftype()

        if dxf_type == "LINE" and len(new_points) >= 2:
            entity.dxf.start = (new_points[0]["x"], new_points[0]["y"], 0)
            entity.dxf.end = (new_points[1]["x"], new_points[1]["y"], 0)
        elif dxf_type == "LWPOLYLINE":
            pts = [(p["x"], p["y"]) for p in new_points]
            entity.set_points(pts, format="xy")
        else:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Cannot modify geometry on {dxf_type}",
            )

        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=op.target_handle,
            description=f"Geometry modified on {dxf_type}",
        )

    def _apply_modify_attributes(self, op: RevisionOp) -> AppliedRevisionOp:
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedRevisionOp(
                op_id=op.op_id,
                op_type=op.op_type,
                success=False,
                error=f"Entity {op.target_handle} not found",
            )

        for key, value in op.forward.items():
            try:
                setattr(entity.dxf, key, value)
            except Exception as exc:
                return AppliedRevisionOp(
                    op_id=op.op_id,
                    op_type=op.op_type,
                    success=False,
                    error=f"Failed to set {key}={value}: {exc}",
                )

        return AppliedRevisionOp(
            op_id=op.op_id,
            op_type=op.op_type,
            success=True,
            entity_handle=op.target_handle,
            description=f"Attributes modified: {list(op.forward.keys())}",
        )
