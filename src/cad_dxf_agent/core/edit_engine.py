"""Edit engine — applies validated operations to a DXF document in memory."""

from __future__ import annotations

import logging
import math
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

from ..models.ops_schema import AppliedChange, ChangeSet, EditOperation, OpType
from ..otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class EditEngine:
    """Applies structured operations to a DXF document.

    Operates on a working copy — never modifies the original file.
    Supports both model space and paper space layouts.
    """

    def __init__(self, dxf_path: str | Path) -> None:
        self.dxf_path = Path(dxf_path)
        self.doc = ezdxf.readfile(str(self.dxf_path))
        self.msp = self.doc.modelspace()
        self._applied: list[AppliedChange] = []

    def _get_layout(self, space: str):
        """Resolve the ezdxf layout object for a space name.

        Returns model space for 'Model', or the named paper space layout.
        Raises KeyError if a named layout doesn't exist.
        """
        if space == "Model":
            return self.msp
        return self.doc.layouts.get(space)

    def apply_changeset(self, changeset: ChangeSet) -> list[AppliedChange]:
        """Apply all operations in a validated changeset.

        Returns list of AppliedChange records.
        """
        with tracer.start_as_current_span("cad.apply_changeset") as span:
            span.set_attribute("cad.ops.count", changeset.op_count)
            results = []
            for op in changeset.operations:
                result = self._apply_operation(op)
                results.append(result)
                self._applied.append(result)
            span.set_attribute("cad.ops.success_count", sum(1 for r in results if r.success))
            return results

    def save(self, output_path: str | Path) -> Path:
        """Save the modified document to a new path."""
        with tracer.start_as_current_span("cad.save") as span:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.doc.saveas(str(output_path))
            span.set_attribute("cad.save.output_basename", output_path.name)
            logger.info("Saved edited DXF to: %s", output_path)
            return output_path

    @property
    def applied_changes(self) -> list[AppliedChange]:
        return list(self._applied)

    def _apply_operation(self, op: EditOperation) -> AppliedChange:
        """Apply a single operation. Assumes validation has already passed."""
        handlers = {
            OpType.MOVE_ENTITY: self._apply_move,
            OpType.EDIT_TEXT: self._apply_edit_text,
            OpType.DELETE_ENTITY: self._apply_delete,
            OpType.ADD_BLOCK: self._apply_add_block,
            OpType.ROTATE_ENTITY: self._apply_rotate,
            OpType.COPY_ENTITY: self._apply_copy,
            OpType.SCALE_ENTITY: self._apply_scale,
            OpType.MIRROR_ENTITY: self._apply_mirror,
            OpType.ADD_LINE: self._apply_add_line,
            OpType.ADD_POLYLINE: self._apply_add_polyline,
            OpType.ADD_CIRCLE: self._apply_add_circle,
            OpType.ADD_ARC: self._apply_add_arc,
            OpType.ADD_TEXT: self._apply_add_text,
        }
        handler = handlers.get(op.op_type)
        if handler is None:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Unknown op type: {op.op_type}",
            )
        return handler(op)

    def _find_entity(self, handle: str):
        """Find entity by handle in model space."""
        return self.doc.entitydb.get(handle)

    # --- V1 operations ---

    def _apply_move(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

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
            return AppliedChange(operation=op, success=False, description=f"Move failed: {e}")

    def _apply_edit_text(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

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
            return AppliedChange(operation=op, success=False, description=f"Edit text failed: {e}")

    def _apply_delete(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

        try:
            layout = self._get_layout(op.target_space)
            layout.delete_entity(entity)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Deleted entity {op.target_handle}",
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Delete failed: {e}")

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

            layout = self._get_layout(op.target_space)

            attribs = {}
            if op.target_layer:
                attribs["layer"] = op.target_layer

            ref = layout.add_blockref(
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
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Add block failed: {e}")

    # --- V2 transform operations ---

    def _apply_rotate(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

        angle = op.params.get("angle", 0)
        cx = op.params.get("cx", 0)
        cy = op.params.get("cy", 0)

        try:
            # ezdxf rotation is around Z axis using a transformation matrix
            m = Matrix44.z_rotate(math.radians(angle))
            # Translate to origin, rotate, translate back
            m = Matrix44.translate(-cx, -cy, 0) @ m @ Matrix44.translate(cx, cy, 0)
            entity.transform(m)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Rotated entity {op.target_handle} by {angle}° around ({cx}, {cy})",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Rotate failed: {e}")

    def _apply_copy(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

        dx = op.params.get("dx", 0)
        dy = op.params.get("dy", 0)

        try:
            layout = self._get_layout(op.target_space)
            # Copy the entity within the same layout
            new_entity = entity.copy()
            layout.add_entity(new_entity)
            new_entity.translate(dx, dy, 0)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=new_entity.dxf.handle,
                description=f"Copied entity {op.target_handle} with offset ({dx}, {dy})",
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Copy failed: {e}")

    def _apply_scale(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

        factor = op.params.get("factor", 1.0)
        cx = op.params.get("cx", 0)
        cy = op.params.get("cy", 0)

        try:
            # Scale around a center point using transformation matrix
            m = (
                Matrix44.translate(-cx, -cy, 0)
                @ Matrix44.scale(factor, factor, 1)
                @ Matrix44.translate(cx, cy, 0)
            )
            entity.transform(m)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Scaled entity {op.target_handle} by {factor}x around ({cx}, {cy})",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Scale failed: {e}")

    def _apply_mirror(self, op: EditOperation) -> AppliedChange:
        assert op.target_handle is not None
        entity = self._find_entity(op.target_handle)
        if entity is None:
            return AppliedChange(operation=op, success=False, description="Entity not found")

        axis = op.params.get("axis", "x")
        value = op.params.get("value", 0)

        try:
            if axis == "x":
                # Mirror across a horizontal line at y=value
                # Translate so mirror line is at origin, flip Y, translate back
                m = (
                    Matrix44.translate(0, -value, 0)
                    @ Matrix44.scale(1, -1, 1)
                    @ Matrix44.translate(0, value, 0)
                )
            elif axis == "y":
                # Mirror across a vertical line at x=value
                m = (
                    Matrix44.translate(-value, 0, 0)
                    @ Matrix44.scale(-1, 1, 1)
                    @ Matrix44.translate(value, 0, 0)
                )
            else:
                return AppliedChange(
                    operation=op,
                    success=False,
                    description=f"Invalid mirror axis: {axis}. Use 'x' or 'y'.",
                )

            entity.transform(m)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=op.target_handle,
                description=f"Mirrored entity {op.target_handle} across {axis}={value}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Mirror failed: {e}")

    # --- V2 entity creation operations ---

    def _apply_add_line(self, op: EditOperation) -> AppliedChange:
        start = op.params.get("start", {})
        end = op.params.get("end", {})
        layer = op.params.get("layer") or op.target_layer

        try:
            layout = self._get_layout(op.target_space)
            attribs = {}
            if layer:
                attribs["layer"] = layer

            entity = layout.add_line(
                (start.get("x", 0), start.get("y", 0)),
                (end.get("x", 0), end.get("y", 0)),
                dxfattribs=attribs,
            )
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=entity.dxf.handle,
                description=(
                    f"Added line from ({start.get('x', 0)}, {start.get('y', 0)}) "
                    f"to ({end.get('x', 0)}, {end.get('y', 0)})"
                ),
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Add line failed: {e}")

    def _apply_add_polyline(self, op: EditOperation) -> AppliedChange:
        points = op.params.get("points", [])
        closed = op.params.get("closed", False)
        layer = op.params.get("layer") or op.target_layer

        try:
            layout = self._get_layout(op.target_space)
            attribs = {}
            if layer:
                attribs["layer"] = layer

            pts = [(p.get("x", 0), p.get("y", 0)) for p in points]
            entity = layout.add_lwpolyline(pts, close=closed, dxfattribs=attribs)
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=entity.dxf.handle,
                description=f"Added polyline with {len(pts)} points (closed={closed})",
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(
                operation=op, success=False, description=f"Add polyline failed: {e}"
            )

    def _apply_add_circle(self, op: EditOperation) -> AppliedChange:
        center = op.params.get("center", {})
        radius = op.params.get("radius", 1.0)
        layer = op.params.get("layer") or op.target_layer

        try:
            layout = self._get_layout(op.target_space)
            attribs = {}
            if layer:
                attribs["layer"] = layer

            entity = layout.add_circle(
                (center.get("x", 0), center.get("y", 0)),
                radius=radius,
                dxfattribs=attribs,
            )
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=entity.dxf.handle,
                description=(
                    f"Added circle at ({center.get('x', 0)}, {center.get('y', 0)}) r={radius}"
                ),
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Add circle failed: {e}")

    def _apply_add_arc(self, op: EditOperation) -> AppliedChange:
        center = op.params.get("center", {})
        radius = op.params.get("radius", 1.0)
        start_angle = op.params.get("start_angle", 0)
        end_angle = op.params.get("end_angle", 90)
        layer = op.params.get("layer") or op.target_layer

        try:
            layout = self._get_layout(op.target_space)
            attribs = {}
            if layer:
                attribs["layer"] = layer

            entity = layout.add_arc(
                (center.get("x", 0), center.get("y", 0)),
                radius=radius,
                start_angle=start_angle,
                end_angle=end_angle,
                dxfattribs=attribs,
            )
            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=entity.dxf.handle,
                description=(
                    f"Added arc at ({center.get('x', 0)}, {center.get('y', 0)}) "
                    f"r={radius} {start_angle}°-{end_angle}°"
                ),
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Add arc failed: {e}")

    def _apply_add_text(self, op: EditOperation) -> AppliedChange:
        text = op.params.get("text", "")
        insert = op.params.get("insert", {})
        height = op.params.get("height", 2.5)
        rotation = op.params.get("rotation", 0)
        layer = op.params.get("layer") or op.target_layer
        text_type = op.params.get("text_type", "TEXT")

        try:
            layout = self._get_layout(op.target_space)
            attribs = {}
            if layer:
                attribs["layer"] = layer

            ix = insert.get("x", 0)
            iy = insert.get("y", 0)

            if text_type == "MTEXT":
                attribs["char_height"] = height
                attribs["insert"] = (ix, iy)
                if rotation:
                    attribs["rotation"] = rotation
                entity = layout.add_mtext(text, dxfattribs=attribs)
            else:
                attribs["height"] = height
                attribs["insert"] = (ix, iy)
                if rotation:
                    attribs["rotation"] = rotation
                entity = layout.add_text(text, dxfattribs=attribs)

            return AppliedChange(
                operation=op,
                success=True,
                entity_handle=entity.dxf.handle,
                description=f"Added {text_type} '{text[:30]}' at ({ix}, {iy})",
            )
        except KeyError:
            return AppliedChange(
                operation=op,
                success=False,
                description=f"Layout not found: {op.target_space}",
            )
        except Exception as e:
            return AppliedChange(operation=op, success=False, description=f"Add text failed: {e}")
