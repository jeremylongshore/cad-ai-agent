"""Tool executor — runs CAD tools invoked by the LLM agent.

Maps tool names to EntityIndex / drawing context operations.
Edit tools (move, delete, edit_text, add_block, rotate, copy, scale,
mirror, add_line, add_polyline, add_circle, add_arc, add_text) accumulate
EditOperation objects instead of mutating the drawing directly.
The operations are later validated and applied by the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.entity_index import EntityIndex
from ..models.cad_schema import DrawingContext, EntityRef
from ..models.ops_schema import EditOperation, OpType

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes CAD tool calls against a DrawingContext.

    Query tools return results immediately.
    Edit tools accumulate EditOperation objects for later validation.
    """

    def __init__(
        self,
        context: DrawingContext,
        protected_layers: list[str] | None = None,
    ) -> None:
        self._context = context
        self._index = EntityIndex(context)
        self._protected = [p.upper() for p in (protected_layers or [])]
        self._operations: list[EditOperation] = []

    @property
    def operations(self) -> list[EditOperation]:
        """Accumulated edit operations from tool calls."""
        return list(self._operations)

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return a JSON-serializable result.

        Raises KeyError for unknown tool names.
        """
        dispatch = {
            # Query tools
            "find_entities": self._find_entities,
            "get_entity": self._get_entity,
            "find_nearest": self._find_nearest,
            "list_layers": self._list_layers,
            "is_protected": self._is_protected,
            # V1 edit tools
            "move_entity": self._move_entity,
            "edit_text": self._edit_text,
            "delete_entity": self._delete_entity,
            "add_block": self._add_block,
            # V2 transform tools
            "rotate_entity": self._rotate_entity,
            "copy_entity": self._copy_entity,
            "scale_entity": self._scale_entity,
            "mirror_entity": self._mirror_entity,
            # V2 creation tools
            "add_line": self._add_line,
            "add_polyline": self._add_polyline,
            "add_circle": self._add_circle,
            "add_arc": self._add_arc,
            "add_text": self._add_text,
            # V3 batch tools
            "batch_move": self._batch_move,
            "batch_rotate": self._batch_rotate,
            "batch_scale": self._batch_scale,
            "batch_delete": self._batch_delete,
            "batch_edit_text": self._batch_edit_text,
        }

        handler = dispatch.get(tool_name)
        if handler is None:
            raise KeyError(f"Unknown tool: {tool_name}")

        logger.debug("Executing tool: %s(%s)", tool_name, args)
        return handler(args)

    # --- Query tools ---

    def _find_entities(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        entity_type = args.get("entity_type")
        text_contains = args.get("text_contains")
        limit = int(args.get("limit", 50))

        candidates = self._index.filter(layer=layer, entity_type=entity_type)

        if text_contains:
            text_matches = self._index.search_text(text_contains)
            match_handles = {e.handle for e in text_matches}
            candidates = [e for e in candidates if e.handle in match_handles]

        total = len(candidates)
        return {
            "count": total,
            "entities": [_entity_to_dict(e) for e in candidates[:limit]],
            "truncated": total > limit,
        }

    def _get_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        return _entity_to_dict(entity)

    def _find_nearest(self, args: dict[str, Any]) -> dict[str, Any]:
        x = args["x"]
        y = args["y"]
        radius = args.get("radius")

        if radius is not None:
            # Spatial window query — return all entities within radius
            results = self._index.find_in_radius(
                x,
                y,
                float(radius),
                entity_type=args.get("entity_type"),
                layer=args.get("layer"),
            )
            if not results:
                return {"error": "No matching entities found within radius"}
            return {
                "count": len(results),
                "entities": [_entity_to_dict(e) for e in results[:50]],
            }

        entity = self._index.nearest(
            x,
            y,
            entity_type=args.get("entity_type"),
            layer=args.get("layer"),
        )
        if entity is None:
            return {"error": "No matching entity found near that point"}
        return _entity_to_dict(entity)

    def _list_layers(self, args: dict[str, Any]) -> dict[str, Any]:
        layers = []
        for layer in self._context.layers:
            layers.append(
                {
                    "name": layer.name,
                    "protected": layer.name.upper() in self._protected,
                    "visible": layer.visible,
                    "frozen": layer.frozen,
                    "entity_count": len(self._index.get_by_layer(layer.name)),
                }
            )
        return {"layers": layers}

    def _is_protected(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args["layer"]
        return {
            "layer": layer,
            "protected": layer.upper() in self._protected,
        }

    # --- V1 edit tools (accumulate operations) ---

    def _move_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot move entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={"dx": args["dx"], "dy": args["dy"]},
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "move_entity",
            "handle": handle,
            "dx": args["dx"],
            "dy": args["dy"],
        }

    def _edit_text(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot edit entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.EDIT_TEXT,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={"new_text": args["new_text"]},
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "edit_text",
            "handle": handle,
            "new_text": args["new_text"],
        }

    def _delete_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot delete entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.DELETE_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "delete_entity",
            "handle": handle,
        }

    def _add_block(self, args: dict[str, Any]) -> dict[str, Any]:
        block_name = args["block_name"]
        x = args["x"]
        y = args["y"]
        layer = args.get("layer")
        space = args.get("space", "Model")

        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot insert block on protected layer: {layer}"}

        op = EditOperation(
            op_type=OpType.ADD_BLOCK,
            target_layer=layer,
            target_space=space,
            params={
                "block_name": block_name,
                "insert_point": {"x": x, "y": y},
                "scale": args.get("scale", 1.0),
                "rotation": args.get("rotation", 0.0),
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_block",
            "block_name": block_name,
            "x": x,
            "y": y,
        }

    # --- V2 transform tools ---

    def _rotate_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot rotate entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.ROTATE_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={
                "angle": args["angle"],
                "cx": args.get("cx", 0),
                "cy": args.get("cy", 0),
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "rotate_entity",
            "handle": handle,
            "angle": args["angle"],
        }

    def _copy_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot copy entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.COPY_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={"dx": args["dx"], "dy": args["dy"]},
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "copy_entity",
            "handle": handle,
            "dx": args["dx"],
            "dy": args["dy"],
        }

    def _scale_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot scale entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.SCALE_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={
                "factor": args["factor"],
                "cx": args.get("cx", 0),
                "cy": args.get("cy", 0),
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "scale_entity",
            "handle": handle,
            "factor": args["factor"],
        }

    def _mirror_entity(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = args["handle"]
        entity = self._index.get_by_handle(handle)
        if entity is None:
            return {"error": f"Entity not found: {handle}"}
        if entity.layer.upper() in self._protected:
            return {"error": f"Cannot mirror entity on protected layer: {entity.layer}"}

        op = EditOperation(
            op_type=OpType.MIRROR_ENTITY,
            target_handle=handle,
            target_layer=entity.layer,
            target_space=entity.space,
            params={
                "axis": args["axis"],
                "value": args.get("value", 0),
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "mirror_entity",
            "handle": handle,
            "axis": args["axis"],
        }

    # --- V2 creation tools ---

    def _add_line(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot create entity on protected layer: {layer}"}

        # Accept both Point2D objects and flat coordinates for backward compat
        start = args.get("start") or {"x": args.get("start_x", 0), "y": args.get("start_y", 0)}
        end = args.get("end") or {"x": args.get("end_x", 0), "y": args.get("end_y", 0)}

        op = EditOperation(
            op_type=OpType.ADD_LINE,
            target_layer=layer,
            params={"start": start, "end": end, "layer": layer},
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_line",
            "start": start,
            "end": end,
        }

    def _add_polyline(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot create entity on protected layer: {layer}"}

        points = args["points"]
        closed = args.get("closed", False)

        op = EditOperation(
            op_type=OpType.ADD_POLYLINE,
            target_layer=layer,
            params={
                "points": points,
                "closed": closed,
                "layer": layer,
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_polyline",
            "point_count": len(points),
            "closed": closed,
        }

    def _add_circle(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot create entity on protected layer: {layer}"}

        # Accept both Point2D object and flat coordinates
        center = args.get("center") or {"x": args.get("center_x", 0), "y": args.get("center_y", 0)}

        op = EditOperation(
            op_type=OpType.ADD_CIRCLE,
            target_layer=layer,
            params={"center": center, "radius": args["radius"], "layer": layer},
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_circle",
            "center": center,
            "radius": args["radius"],
        }

    def _add_arc(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot create entity on protected layer: {layer}"}

        # Accept both Point2D object and flat coordinates
        center = args.get("center") or {"x": args.get("center_x", 0), "y": args.get("center_y", 0)}

        op = EditOperation(
            op_type=OpType.ADD_ARC,
            target_layer=layer,
            params={
                "center": center,
                "radius": args["radius"],
                "start_angle": args["start_angle"],
                "end_angle": args["end_angle"],
                "layer": layer,
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_arc",
            "center": center,
            "radius": args["radius"],
        }

    def _add_text(self, args: dict[str, Any]) -> dict[str, Any]:
        layer = args.get("layer")
        if layer and layer.upper() in self._protected:
            return {"error": f"Cannot create entity on protected layer: {layer}"}

        text_type = args.get("text_type", "TEXT")

        # Accept both Point2D object and flat coordinates
        insert = args.get("insert") or {"x": args.get("x", 0), "y": args.get("y", 0)}

        op = EditOperation(
            op_type=OpType.ADD_TEXT,
            target_layer=layer,
            params={
                "text": args["text"],
                "insert": insert,
                "height": args.get("height", 2.5),
                "rotation": args.get("rotation", 0),
                "text_type": text_type,
                "layer": layer,
            },
        )
        self._operations.append(op)
        return {
            "status": "queued",
            "operation": "add_text",
            "text": args["text"],
            "insert": insert,
        }


    # --- V3 batch tools ---

    def _resolve_batch_filter(
        self, args: dict[str, Any]
    ) -> list[EntityRef] | dict[str, Any]:
        """Apply filter criteria and return matching entities.

        Returns list[EntityRef] on success, or error dict if no filters
        or no matches.
        """
        layer = args.get("layer")
        entity_type = args.get("entity_type")
        text_contains = args.get("text_contains")
        center_x = args.get("center_x")
        center_y = args.get("center_y")
        radius = args.get("radius")

        has_filter = any([
            layer, entity_type, text_contains,
            (center_x is not None and center_y is not None and radius),
        ])
        if not has_filter:
            return {
                "error": (
                    "At least one filter is required (layer, entity_type, "
                    "text_contains, or center_x/center_y/radius)"
                )
            }

        # Spatial filter first if specified
        if (
            center_x is not None
            and center_y is not None
            and radius is not None
        ):
            candidates = self._index.find_in_radius(
                float(center_x),
                float(center_y),
                float(radius),
                entity_type=entity_type,
                layer=layer,
            )
        else:
            candidates = self._index.filter(
                layer=layer, entity_type=entity_type
            )

        # Text filter
        if text_contains:
            text_matches = self._index.search_text(text_contains)
            match_handles = {e.handle for e in text_matches}
            candidates = [
                e for e in candidates if e.handle in match_handles
            ]

        # Exclude protected layers
        candidates = [
            e for e in candidates
            if e.layer.upper() not in self._protected
        ]

        if not candidates:
            return {"error": "No matching entities found"}

        return candidates

    def _batch_move(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._resolve_batch_filter(args)
        if isinstance(result, dict):
            return result

        dx, dy = args["dx"], args["dy"]
        for entity in result:
            op = EditOperation(
                op_type=OpType.MOVE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_space=entity.space,
                params={"dx": dx, "dy": dy},
            )
            self._operations.append(op)

        return {
            "status": "queued",
            "operation": "batch_move",
            "matched": len(result),
            "dx": dx,
            "dy": dy,
        }

    def _batch_rotate(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._resolve_batch_filter(args)
        if isinstance(result, dict):
            return result

        angle = args["angle"]
        # If cx/cy given, use shared center; otherwise each entity rotates
        # around its own insert_point (cx=cy=0 means use entity center)
        cx = args.get("cx")
        cy = args.get("cy")

        for entity in result:
            params: dict[str, Any] = {"angle": angle}
            if cx is not None and cy is not None:
                params["cx"] = cx
                params["cy"] = cy
            elif entity.insert_point:
                params["cx"] = entity.insert_point.x
                params["cy"] = entity.insert_point.y
            else:
                params["cx"] = 0
                params["cy"] = 0

            op = EditOperation(
                op_type=OpType.ROTATE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_space=entity.space,
                params=params,
            )
            self._operations.append(op)

        return {
            "status": "queued",
            "operation": "batch_rotate",
            "matched": len(result),
            "angle": angle,
        }

    def _batch_scale(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._resolve_batch_filter(args)
        if isinstance(result, dict):
            return result

        factor = args["factor"]
        cx = args.get("cx")
        cy = args.get("cy")

        for entity in result:
            params: dict[str, Any] = {"factor": factor}
            if cx is not None and cy is not None:
                params["cx"] = cx
                params["cy"] = cy
            elif entity.insert_point:
                params["cx"] = entity.insert_point.x
                params["cy"] = entity.insert_point.y
            else:
                params["cx"] = 0
                params["cy"] = 0

            op = EditOperation(
                op_type=OpType.SCALE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_space=entity.space,
                params=params,
            )
            self._operations.append(op)

        return {
            "status": "queued",
            "operation": "batch_scale",
            "matched": len(result),
            "factor": factor,
        }

    def _batch_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._resolve_batch_filter(args)
        if isinstance(result, dict):
            return result

        for entity in result:
            op = EditOperation(
                op_type=OpType.DELETE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_space=entity.space,
            )
            self._operations.append(op)

        return {
            "status": "queued",
            "operation": "batch_delete",
            "matched": len(result),
        }

    def _batch_edit_text(self, args: dict[str, Any]) -> dict[str, Any]:
        find_str = args["find"]
        replace_str = args["replace"]

        result = self._resolve_batch_filter(args)
        if isinstance(result, dict):
            return result

        # Further filter: only TEXT/MTEXT with the find string
        text_entities = [
            e for e in result
            if e.entity_type.value in ("TEXT", "MTEXT")
            and e.text_content
            and find_str in e.text_content
        ]

        if not text_entities:
            return {"error": f"No text entities contain '{find_str}'"}

        for entity in text_entities:
            new_text = entity.text_content.replace(find_str, replace_str)
            op = EditOperation(
                op_type=OpType.EDIT_TEXT,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_space=entity.space,
                params={"new_text": new_text},
            )
            self._operations.append(op)

        return {
            "status": "queued",
            "operation": "batch_edit_text",
            "matched": len(text_entities),
            "find": find_str,
            "replace": replace_str,
        }


def _entity_to_dict(entity: EntityRef) -> dict[str, Any]:
    """Convert an EntityRef to a JSON-serializable dict for tool results."""
    d: dict[str, Any] = {
        "handle": entity.handle,
        "type": entity.entity_type.value,
        "layer": entity.layer,
        "space": entity.space,
    }
    if entity.insert_point:
        d["x"] = entity.insert_point.x
        d["y"] = entity.insert_point.y
    if entity.text_content:
        d["text"] = entity.text_content
    if entity.block_name:
        d["block_name"] = entity.block_name
    if entity.attributes:
        d["attributes"] = entity.attributes
    if entity.text_geometry:
        tg = entity.text_geometry
        d["text_geometry"] = {
            "height": tg.effective_height,
            "rotation": tg.rotation,
            "provenance": tg.provenance.value,
        }
    return d
