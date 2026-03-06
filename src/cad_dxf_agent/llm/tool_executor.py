"""Tool executor — runs CAD tools invoked by the LLM agent.

Maps tool names to EntityIndex / drawing context operations.
Edit tools (move, delete, edit_text, add_block) accumulate
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
            "find_entities": self._find_entities,
            "get_entity": self._get_entity,
            "find_nearest": self._find_nearest,
            "list_layers": self._list_layers,
            "is_protected": self._is_protected,
            "move_entity": self._move_entity,
            "edit_text": self._edit_text,
            "delete_entity": self._delete_entity,
            "add_block": self._add_block,
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

    # --- Edit tools (accumulate operations) ---

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
