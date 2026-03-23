"""CAD tool definitions for Gemini function calling.

Defines the tool schemas that the LLM agent can invoke to query and
edit the drawing. Each tool wraps existing EntityIndex / EditEngine
methods. The LLM never touches DXF directly — it calls these tools,
and the host code executes them against the validated pipeline.
"""

import dataclasses
import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Tool schemas for Gemini function calling
# ---------------------------------------------------------------------------
# Each dict follows the Gemini FunctionDeclaration schema:
#   name, description, parameters (JSON Schema object)
# ---------------------------------------------------------------------------

_ALL_ENTITY_TYPES = [
    "LINE",
    "LWPOLYLINE",
    "TEXT",
    "MTEXT",
    "INSERT",
    "CIRCLE",
    "ARC",
    "DIMENSION",
    "HATCH",
    "SPLINE",
    "POLYLINE",
    "ELLIPSE",
    "MLEADER",
    "SOLID",
    "LEADER",
]

FIND_ENTITIES = {
    "name": "find_entities",
    "description": (
        "Search for entities in the drawing by layer, type, and/or text content. "
        "Returns a list of matching entities with handle, type, layer, position, and text. "
        "Results are limited to the first `limit` matches (default 50)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "description": "Filter by layer name (case-insensitive). Example: 'STRUCTURAL'",
            },
            "entity_type": {
                "type": "string",
                "description": (
                    "Filter by entity type. Supported types: LINE, LWPOLYLINE, TEXT, MTEXT, "
                    "INSERT, CIRCLE, ARC, DIMENSION, HATCH, SPLINE, POLYLINE, ELLIPSE, "
                    "MLEADER, SOLID, LEADER"
                ),
                "enum": _ALL_ENTITY_TYPES,
            },
            "text_contains": {
                "type": "string",
                "description": (
                    "Search for entities whose text contains this string (case-insensitive)"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of entities to return (default 50)",
            },
        },
        "required": [],
    },
}

GET_ENTITY = {
    "name": "get_entity",
    "description": (
        "Get full details of a single entity by its handle (unique ID). "
        "Returns handle, type, layer, position, text content, and block name."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "The DXF entity handle (unique identifier)",
            },
        },
        "required": ["handle"],
    },
}

FIND_NEAREST = {
    "name": "find_nearest",
    "description": (
        "Find the nearest entity to a given point. Useful for locating entities "
        "at grid intersections or near specific coordinates. "
        "Use `radius` to limit the search to a spatial window."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "x": {"type": "number", "description": "X coordinate in drawing units"},
            "y": {"type": "number", "description": "Y coordinate in drawing units"},
            "entity_type": {
                "type": "string",
                "description": "Optional type filter",
                "enum": _ALL_ENTITY_TYPES,
            },
            "layer": {
                "type": "string",
                "description": "Optional layer filter (case-insensitive)",
            },
            "radius": {
                "type": "number",
                "description": (
                    "Optional search radius in drawing units. "
                    "Only entities within this distance are considered."
                ),
            },
        },
        "required": ["x", "y"],
    },
}

LIST_LAYERS = {
    "name": "list_layers",
    "description": (
        "List all layers in the drawing with their protection status and entity counts."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

IS_PROTECTED = {
    "name": "is_protected",
    "description": "Check whether a layer is protected from editing.",
    "parameters": {
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "description": "The layer name to check",
            },
        },
        "required": ["layer"],
    },
}

# ---------------------------------------------------------------------------
# V1 edit tools
# ---------------------------------------------------------------------------

MOVE_ENTITY = {
    "name": "move_entity",
    "description": (
        "Move an entity by a displacement vector (dx, dy) in drawing units. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to move",
            },
            "dx": {
                "type": "number",
                "description": "Displacement in X direction (drawing units)",
            },
            "dy": {
                "type": "number",
                "description": "Displacement in Y direction (drawing units)",
            },
        },
        "required": ["handle", "dx", "dy"],
    },
}

EDIT_TEXT = {
    "name": "edit_text",
    "description": (
        "Change the text content of a TEXT or MTEXT entity. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the TEXT/MTEXT entity to edit",
            },
            "new_text": {
                "type": "string",
                "description": "The new text content",
            },
        },
        "required": ["handle", "new_text"],
    },
}

DELETE_ENTITY = {
    "name": "delete_entity",
    "description": (
        "Delete an entity from the drawing. Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to delete",
            },
        },
        "required": ["handle"],
    },
}

ADD_BLOCK = {
    "name": "add_block",
    "description": (
        "Insert a block reference at a specified point. "
        "The block must exist in the drawing's block definitions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "block_name": {
                "type": "string",
                "description": "Name of the block definition to insert",
            },
            "x": {
                "type": "number",
                "description": "X coordinate for insertion point",
            },
            "y": {
                "type": "number",
                "description": "Y coordinate for insertion point",
            },
            "layer": {
                "type": "string",
                "description": "Optional target layer for the block reference",
            },
            "scale": {
                "type": "number",
                "description": "Uniform scale factor (default 1.0)",
            },
            "rotation": {
                "type": "number",
                "description": "Rotation angle in degrees (default 0)",
            },
        },
        "required": ["block_name", "x", "y"],
    },
}

# ---------------------------------------------------------------------------
# V2 transform tools
# ---------------------------------------------------------------------------

ROTATE_ENTITY = {
    "name": "rotate_entity",
    "description": (
        "Rotate an entity by a given angle in degrees. "
        "Rotation center defaults to origin (0,0) unless cx, cy are specified. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to rotate",
            },
            "angle": {
                "type": "number",
                "description": "Rotation angle in degrees (positive = counter-clockwise)",
            },
            "cx": {
                "type": "number",
                "description": "X coordinate of rotation center (default 0)",
            },
            "cy": {
                "type": "number",
                "description": "Y coordinate of rotation center (default 0)",
            },
        },
        "required": ["handle", "angle"],
    },
}

COPY_ENTITY = {
    "name": "copy_entity",
    "description": (
        "Create a copy of an entity at an offset position. "
        "The original entity is preserved. The copy gets a new handle. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to copy",
            },
            "dx": {
                "type": "number",
                "description": "X offset for the copy from original position",
            },
            "dy": {
                "type": "number",
                "description": "Y offset for the copy from original position",
            },
        },
        "required": ["handle", "dx", "dy"],
    },
}

SCALE_ENTITY = {
    "name": "scale_entity",
    "description": (
        "Scale an entity by a uniform factor relative to a center point. "
        "Center defaults to origin (0,0) unless cx, cy are specified. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to scale",
            },
            "factor": {
                "type": "number",
                "description": "Scale factor (>1 enlarges, <1 shrinks, must be non-zero)",
            },
            "cx": {
                "type": "number",
                "description": "X coordinate of scale center (default 0)",
            },
            "cy": {
                "type": "number",
                "description": "Y coordinate of scale center (default 0)",
            },
        },
        "required": ["handle", "factor"],
    },
}

MIRROR_ENTITY = {
    "name": "mirror_entity",
    "description": (
        "Mirror an entity across an axis line. "
        "axis='x' mirrors across horizontal line y=value. "
        "axis='y' mirrors across vertical line x=value. "
        "Cannot target entities on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "Handle of the entity to mirror",
            },
            "axis": {
                "type": "string",
                "enum": ["x", "y"],
                "description": "Mirror axis: 'x' for horizontal, 'y' for vertical",
            },
            "value": {
                "type": "number",
                "description": "Position of the mirror line (default 0)",
            },
        },
        "required": ["handle", "axis"],
    },
}

# ---------------------------------------------------------------------------
# V2 entity creation tools
# ---------------------------------------------------------------------------

_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
    },
    "required": ["x", "y"],
}

ADD_LINE = {
    "name": "add_line",
    "description": ("Draw a new line between two points. Cannot create on protected layers."),
    "parameters": {
        "type": "object",
        "properties": {
            "start": {
                **_POINT_SCHEMA,
                "description": "Start point {x, y}",
            },
            "end": {
                **_POINT_SCHEMA,
                "description": "End point {x, y}",
            },
            "layer": {
                "type": "string",
                "description": "Target layer name (optional)",
            },
        },
        "required": ["start", "end"],
    },
}

ADD_POLYLINE = {
    "name": "add_polyline",
    "description": (
        "Draw a new polyline through a series of points. "
        "Set closed=true to close the shape. "
        "Cannot create on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                    "required": ["x", "y"],
                },
                "description": "List of {x, y} points defining the polyline (minimum 2)",
            },
            "closed": {
                "type": "boolean",
                "description": "Whether to close the polyline (default false)",
            },
            "layer": {
                "type": "string",
                "description": "Target layer name (optional)",
            },
        },
        "required": ["points"],
    },
}

ADD_CIRCLE = {
    "name": "add_circle",
    "description": (
        "Draw a new circle at a center point with a given radius. "
        "Cannot create on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "center": {
                **_POINT_SCHEMA,
                "description": "Center point {x, y}",
            },
            "radius": {
                "type": "number",
                "description": "Circle radius in drawing units",
            },
            "layer": {
                "type": "string",
                "description": "Target layer name (optional)",
            },
        },
        "required": ["center", "radius"],
    },
}

ADD_ARC = {
    "name": "add_arc",
    "description": (
        "Draw a new arc (portion of a circle) defined by center, radius, "
        "start angle, and end angle in degrees. "
        "Cannot create on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "center": {
                **_POINT_SCHEMA,
                "description": "Center point {x, y}",
            },
            "radius": {
                "type": "number",
                "description": "Arc radius in drawing units",
            },
            "start_angle": {
                "type": "number",
                "description": "Start angle in degrees (0 = east/right)",
            },
            "end_angle": {
                "type": "number",
                "description": "End angle in degrees (counter-clockwise from start)",
            },
            "layer": {
                "type": "string",
                "description": "Target layer name (optional)",
            },
        },
        "required": ["center", "radius", "start_angle", "end_angle"],
    },
}

ADD_TEXT_TOOL = {
    "name": "add_text",
    "description": (
        "Add a new text annotation at a specified point. "
        "Use text_type='MTEXT' for multi-line text. "
        "Cannot create on protected layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text content to add",
            },
            "insert": {
                **_POINT_SCHEMA,
                "description": "Insertion point {x, y}",
            },
            "height": {
                "type": "number",
                "description": "Text height in drawing units (default 2.5)",
            },
            "rotation": {
                "type": "number",
                "description": "Text rotation in degrees (default 0)",
            },
            "layer": {
                "type": "string",
                "description": "Target layer name (optional)",
            },
            "text_type": {
                "type": "string",
                "enum": ["TEXT", "MTEXT"],
                "description": "TEXT (single line) or MTEXT (multi-line). Default TEXT.",
            },
        },
        "required": ["text", "insert"],
    },
}

# ---------------------------------------------------------------------------
# Batch filter schema (shared across batch tools)
# ---------------------------------------------------------------------------

_BATCH_FILTER_PROPERTIES = {
    "layer": {
        "type": "string",
        "description": "Filter: only entities on this layer",
    },
    "entity_type": {
        "type": "string",
        "description": (
            "Filter: only entities of this type "
            "(LINE, LWPOLYLINE, TEXT, MTEXT, INSERT, CIRCLE, ARC)"
        ),
    },
    "text_contains": {
        "type": "string",
        "description": "Filter: only TEXT/MTEXT containing this substring",
    },
    "center_x": {
        "type": "number",
        "description": "Filter: center X for radius search",
    },
    "center_y": {
        "type": "number",
        "description": "Filter: center Y for radius search",
    },
    "radius": {
        "type": "number",
        "description": "Filter: search radius from (center_x, center_y)",
    },
}

BATCH_MOVE = {
    "name": "batch_move",
    "description": (
        "Move all entities matching the filter criteria by a displacement "
        "vector (dx, dy). At least one filter (layer, entity_type, "
        "text_contains, or radius) is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_BATCH_FILTER_PROPERTIES,
            "dx": {
                "type": "number",
                "description": "Displacement in X direction (drawing units)",
            },
            "dy": {
                "type": "number",
                "description": "Displacement in Y direction (drawing units)",
            },
        },
        "required": ["dx", "dy"],
    },
}

BATCH_ROTATE = {
    "name": "batch_rotate",
    "description": (
        "Rotate all entities matching the filter criteria by a given angle. "
        "At least one filter is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_BATCH_FILTER_PROPERTIES,
            "angle": {
                "type": "number",
                "description": "Rotation angle in degrees (counter-clockwise)",
            },
            "cx": {
                "type": "number",
                "description": "Rotation center X (default: each entity's own center)",
            },
            "cy": {
                "type": "number",
                "description": "Rotation center Y (default: each entity's own center)",
            },
        },
        "required": ["angle"],
    },
}

BATCH_SCALE = {
    "name": "batch_scale",
    "description": (
        "Scale all entities matching the filter criteria by a uniform "
        "factor. At least one filter is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_BATCH_FILTER_PROPERTIES,
            "factor": {
                "type": "number",
                "description": "Scale factor (>1 enlarges, <1 shrinks)",
            },
            "cx": {
                "type": "number",
                "description": "Scale center X (default: each entity's own center)",
            },
            "cy": {
                "type": "number",
                "description": "Scale center Y (default: each entity's own center)",
            },
        },
        "required": ["factor"],
    },
}

BATCH_DELETE = {
    "name": "batch_delete",
    "description": (
        "Delete all entities matching the filter criteria. "
        "At least one filter is required. Use with caution."
    ),
    "parameters": {
        "type": "object",
        "properties": _BATCH_FILTER_PROPERTIES,
        "required": [],
    },
}

BATCH_EDIT_TEXT = {
    "name": "batch_edit_text",
    "description": (
        "Find-and-replace text content across all TEXT/MTEXT entities matching the filter criteria."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_BATCH_FILTER_PROPERTIES,
            "find": {
                "type": "string",
                "description": "Text substring to find",
            },
            "replace": {
                "type": "string",
                "description": "Replacement text",
            },
        },
        "required": ["find", "replace"],
    },
}

# ---------------------------------------------------------------------------
# Query tools (read-only) vs. edit tools (produce operations)
# ---------------------------------------------------------------------------

QUERY_TOOLS = [FIND_ENTITIES, GET_ENTITY, FIND_NEAREST, LIST_LAYERS, IS_PROTECTED]
EDIT_TOOLS = [
    # V1
    MOVE_ENTITY,
    EDIT_TEXT,
    DELETE_ENTITY,
    ADD_BLOCK,
    # V2 transforms
    ROTATE_ENTITY,
    COPY_ENTITY,
    SCALE_ENTITY,
    MIRROR_ENTITY,
    # V2 creation
    ADD_LINE,
    ADD_POLYLINE,
    ADD_CIRCLE,
    ADD_ARC,
    ADD_TEXT_TOOL,
    # V3 batch operations
    BATCH_MOVE,
    BATCH_ROTATE,
    BATCH_SCALE,
    BATCH_DELETE,
    BATCH_EDIT_TEXT,
]
ALL_TOOLS = QUERY_TOOLS + EDIT_TOOLS


def get_tool_by_name(name: str) -> dict[str, Any] | None:
    """Look up a tool definition by name."""
    for tool in ALL_TOOLS:
        if tool["name"] == name:
            return tool
    return None


def is_edit_tool(name: str) -> bool:
    """Return True if the tool name is an edit (mutating) tool."""
    return any(t["name"] == name for t in EDIT_TOOLS)


def get_tools_for_request_class(request_class: str) -> list[dict[str, Any]]:
    """Return the tool subset appropriate for a given RequestClass.

    Only MODIFY requests get the full tool set (query + edit).
    All other request classes (understand, estimate, recommend, optimize,
    summarize, compare, validate) get query-only tools — sending edit
    tools for read-only requests wastes tokens and risks LLM confusion.
    """
    if request_class == "modify":
        return ALL_TOOLS
    return QUERY_TOOLS


# ---------------------------------------------------------------------------
# ADK-pattern typed tool functions
# ---------------------------------------------------------------------------
# Plain Python functions with type hints and docstrings.
# ADK auto-generates JSON Schema from these. These coexist with the
# dict-based definitions above — the dicts remain canonical for now.
# ---------------------------------------------------------------------------


@dataclass
class ToolPoint2D:
    """A 2D point in drawing units (used for schema generation only)."""

    x: float
    y: float


def find_entities_fn(
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    limit: int = 50,
) -> dict:
    """Search for entities in the drawing by layer, type, and/or text content.

    Returns a list of matching entities with handle, type, layer, position, and text.
    Results are limited to the first `limit` matches.

    Args:
        layer: Filter by layer name (case-insensitive). Example: 'STRUCTURAL'
        entity_type: Filter by entity type. Supported: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT,
            CIRCLE, ARC, DIMENSION, HATCH, SPLINE, POLYLINE, ELLIPSE, MLEADER, SOLID, LEADER
        text_contains: Search for entities whose text contains this string (case-insensitive)
        limit: Maximum number of entities to return (default 50)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def get_entity_fn(handle: str) -> dict:
    """Get full details of a single entity by its handle (unique ID).

    Returns handle, type, layer, position, text content, and block name.

    Args:
        handle: The DXF entity handle (unique identifier)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def find_nearest_fn(
    x: float,
    y: float,
    entity_type: str | None = None,
    layer: str | None = None,
    radius: float | None = None,
) -> dict:
    """Find the nearest entity to a given point.

    Useful for locating entities at grid intersections or near specific coordinates.
    Use `radius` to limit the search to a spatial window.

    Args:
        x: X coordinate in drawing units
        y: Y coordinate in drawing units
        entity_type: Optional type filter
        layer: Optional layer filter (case-insensitive)
        radius: Optional search radius in drawing units. Only entities within this distance
            are considered.
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def list_layers_fn() -> dict:
    """List all layers in the drawing with their protection status and entity counts."""
    raise NotImplementedError("Dispatch via ToolExecutor")


def is_protected_fn(layer: str) -> dict:
    """Check whether a layer is protected from editing.

    Args:
        layer: The layer name to check
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


QUERY_TOOL_FUNCTIONS: list[Callable] = [
    find_entities_fn,
    get_entity_fn,
    find_nearest_fn,
    list_layers_fn,
    is_protected_fn,
]

# ---------------------------------------------------------------------------
# Typed stubs for edit tools
# ---------------------------------------------------------------------------


def move_entity_fn(handle: str, dx: float, dy: float) -> dict:
    """Move an entity by a displacement vector (dx, dy) in drawing units.

    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to move
        dx: Displacement in X direction (drawing units)
        dy: Displacement in Y direction (drawing units)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def edit_text_fn(handle: str, new_text: str) -> dict:
    """Change the text content of a TEXT or MTEXT entity.

    Cannot target entities on protected layers.

    Args:
        handle: Handle of the TEXT/MTEXT entity to edit
        new_text: The new text content
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def delete_entity_fn(handle: str) -> dict:
    """Delete an entity from the drawing.

    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to delete
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_block_fn(
    block_name: str,
    x: float,
    y: float,
    layer: str | None = None,
    scale: float | None = None,
    rotation: float | None = None,
) -> dict:
    """Insert a block reference at a specified point.

    The block must exist in the drawing's block definitions.

    Args:
        block_name: Name of the block definition to insert
        x: X coordinate for insertion point
        y: Y coordinate for insertion point
        layer: Optional target layer for the block reference
        scale: Uniform scale factor (default 1.0)
        rotation: Rotation angle in degrees (default 0)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def rotate_entity_fn(
    handle: str,
    angle: float,
    cx: float | None = None,
    cy: float | None = None,
) -> dict:
    """Rotate an entity by a given angle in degrees.

    Rotation center defaults to origin (0,0) unless cx, cy are specified.
    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to rotate
        angle: Rotation angle in degrees (positive = counter-clockwise)
        cx: X coordinate of rotation center (default 0)
        cy: Y coordinate of rotation center (default 0)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def copy_entity_fn(handle: str, dx: float, dy: float) -> dict:
    """Create a copy of an entity at an offset position.

    The original entity is preserved. The copy gets a new handle.
    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to copy
        dx: X offset for the copy from original position
        dy: Y offset for the copy from original position
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def scale_entity_fn(
    handle: str,
    factor: float,
    cx: float | None = None,
    cy: float | None = None,
) -> dict:
    """Scale an entity by a uniform factor relative to a center point.

    Center defaults to origin (0,0) unless cx, cy are specified.
    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to scale
        factor: Scale factor (>1 enlarges, <1 shrinks, must be non-zero)
        cx: X coordinate of scale center (default 0)
        cy: Y coordinate of scale center (default 0)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def mirror_entity_fn(
    handle: str,
    axis: typing.Literal["x", "y"],
    value: float | None = None,
) -> dict:
    """Mirror an entity across an axis line.

    axis='x' mirrors across horizontal line y=value.
    axis='y' mirrors across vertical line x=value.
    Cannot target entities on protected layers.

    Args:
        handle: Handle of the entity to mirror
        axis: Mirror axis: 'x' for horizontal, 'y' for vertical
        value: Position of the mirror line (default 0)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_line_fn(
    start: ToolPoint2D,
    end: ToolPoint2D,
    layer: str | None = None,
) -> dict:
    """Draw a new line between two points.

    Cannot create on protected layers.

    Args:
        start: Start point {x, y}
        end: End point {x, y}
        layer: Target layer name (optional)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_polyline_fn(
    points: list[ToolPoint2D],
    closed: bool = False,
    layer: str | None = None,
) -> dict:
    """Draw a new polyline through a series of points.

    Set closed=true to close the shape.
    Cannot create on protected layers.

    Args:
        points: List of {x, y} points defining the polyline (minimum 2)
        closed: Whether to close the polyline (default false)
        layer: Target layer name (optional)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_circle_fn(
    center: ToolPoint2D,
    radius: float,
    layer: str | None = None,
) -> dict:
    """Draw a new circle at a center point with a given radius.

    Cannot create on protected layers.

    Args:
        center: Center point {x, y}
        radius: Circle radius in drawing units
        layer: Target layer name (optional)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_arc_fn(
    center: ToolPoint2D,
    radius: float,
    start_angle: float,
    end_angle: float,
    layer: str | None = None,
) -> dict:
    """Draw a new arc (portion of a circle) defined by center, radius, start angle, and end angle.

    Angles are in degrees. Cannot create on protected layers.

    Args:
        center: Center point {x, y}
        radius: Arc radius in drawing units
        start_angle: Start angle in degrees (0 = east/right)
        end_angle: End angle in degrees (counter-clockwise from start)
        layer: Target layer name (optional)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def add_text_fn(
    text: str,
    insert: ToolPoint2D,
    height: float | None = None,
    rotation: float | None = None,
    layer: str | None = None,
    text_type: typing.Literal["TEXT", "MTEXT"] | None = None,
) -> dict:
    """Add a new text annotation at a specified point.

    Use text_type='MTEXT' for multi-line text. Cannot create on protected layers.

    Args:
        text: The text content to add
        insert: Insertion point {x, y}
        height: Text height in drawing units (default 2.5)
        rotation: Text rotation in degrees (default 0)
        layer: Target layer name (optional)
        text_type: TEXT (single line) or MTEXT (multi-line). Default TEXT.
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def batch_move_fn(
    dx: float,
    dy: float,
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    radius: float | None = None,
) -> dict:
    """Move all entities matching the filter criteria by a displacement vector (dx, dy).

    At least one filter (layer, entity_type, text_contains, or radius) is required.

    Args:
        dx: Displacement in X direction (drawing units)
        dy: Displacement in Y direction (drawing units)
        layer: Filter: only entities on this layer
        entity_type: Filter: only entities of this type (LINE, LWPOLYLINE, TEXT, MTEXT,
            INSERT, CIRCLE, ARC)
        text_contains: Filter: only TEXT/MTEXT containing this substring
        center_x: Filter: center X for radius search
        center_y: Filter: center Y for radius search
        radius: Filter: search radius from (center_x, center_y)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def batch_rotate_fn(
    angle: float,
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    radius: float | None = None,
    cx: float | None = None,
    cy: float | None = None,
) -> dict:
    """Rotate all entities matching the filter criteria by a given angle.

    At least one filter is required.

    Args:
        angle: Rotation angle in degrees (counter-clockwise)
        layer: Filter: only entities on this layer
        entity_type: Filter: only entities of this type (LINE, LWPOLYLINE, TEXT, MTEXT,
            INSERT, CIRCLE, ARC)
        text_contains: Filter: only TEXT/MTEXT containing this substring
        center_x: Filter: center X for radius search
        center_y: Filter: center Y for radius search
        radius: Filter: search radius from (center_x, center_y)
        cx: Rotation center X (default: each entity's own center)
        cy: Rotation center Y (default: each entity's own center)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def batch_scale_fn(
    factor: float,
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    radius: float | None = None,
    cx: float | None = None,
    cy: float | None = None,
) -> dict:
    """Scale all entities matching the filter criteria by a uniform factor.

    At least one filter is required.

    Args:
        factor: Scale factor (>1 enlarges, <1 shrinks)
        layer: Filter: only entities on this layer
        entity_type: Filter: only entities of this type (LINE, LWPOLYLINE, TEXT, MTEXT,
            INSERT, CIRCLE, ARC)
        text_contains: Filter: only TEXT/MTEXT containing this substring
        center_x: Filter: center X for radius search
        center_y: Filter: center Y for radius search
        radius: Filter: search radius from (center_x, center_y)
        cx: Scale center X (default: each entity's own center)
        cy: Scale center Y (default: each entity's own center)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def batch_delete_fn(
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    radius: float | None = None,
) -> dict:
    """Delete all entities matching the filter criteria.

    At least one filter is required. Use with caution.

    Args:
        layer: Filter: only entities on this layer
        entity_type: Filter: only entities of this type (LINE, LWPOLYLINE, TEXT, MTEXT,
            INSERT, CIRCLE, ARC)
        text_contains: Filter: only TEXT/MTEXT containing this substring
        center_x: Filter: center X for radius search
        center_y: Filter: center Y for radius search
        radius: Filter: search radius from (center_x, center_y)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


def batch_edit_text_fn(
    find: str,
    replace: str,
    layer: str | None = None,
    entity_type: str | None = None,
    text_contains: str | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    radius: float | None = None,
) -> dict:
    """Find-and-replace text content across all TEXT/MTEXT entities matching the filter criteria.

    Args:
        find: Text substring to find
        replace: Replacement text
        layer: Filter: only entities on this layer
        entity_type: Filter: only entities of this type (LINE, LWPOLYLINE, TEXT, MTEXT,
            INSERT, CIRCLE, ARC)
        text_contains: Filter: only TEXT/MTEXT containing this substring
        center_x: Filter: center X for radius search
        center_y: Filter: center Y for radius search
        radius: Filter: search radius from (center_x, center_y)
    """
    raise NotImplementedError("Dispatch via ToolExecutor")


EDIT_TOOL_FUNCTIONS: list[Callable] = [
    move_entity_fn,
    edit_text_fn,
    delete_entity_fn,
    add_block_fn,
    rotate_entity_fn,
    copy_entity_fn,
    scale_entity_fn,
    mirror_entity_fn,
    add_line_fn,
    add_polyline_fn,
    add_circle_fn,
    add_arc_fn,
    add_text_fn,
    batch_move_fn,
    batch_rotate_fn,
    batch_scale_fn,
    batch_delete_fn,
    batch_edit_text_fn,
]

# ---------------------------------------------------------------------------
# Schema generation from typed functions
# ---------------------------------------------------------------------------


def _hint_to_json_schema(hint: Any) -> dict[str, Any]:
    """Convert a Python type hint to a JSON Schema type dict.

    Handles Optional (``X | None``), primitives (str, int, float, bool),
    ``typing.Literal`` (→ enum), dataclasses (→ object with properties),
    ``list[X]`` (→ array with items), and falls back to ``{"type": "string"}``
    for anything unrecognised.
    """
    origin = getattr(hint, "__origin__", None)

    # PEP 604 union: ``str | None`` → types.UnionType (Python 3.10+)
    if isinstance(hint, types.UnionType):
        non_none = [a for a in hint.__args__ if a is not type(None)]
        if len(non_none) == 1:
            return _hint_to_json_schema(non_none[0])

    # typing.Union / typing.Optional (older style)
    if origin is typing.Union:
        non_none = [a for a in hint.__args__ if a is not type(None)]
        if len(non_none) == 1:
            return _hint_to_json_schema(non_none[0])

    # typing.Literal["x", "y"] → {"type": "string", "enum": ["x", "y"]}
    if origin is typing.Literal:
        args = typing.get_args(hint)
        if args:
            # Infer JSON type from the first literal value
            first = args[0]
            if isinstance(first, bool):
                json_type = "boolean"
            elif isinstance(first, int):
                json_type = "integer"
            elif isinstance(first, float):
                json_type = "number"
            else:
                json_type = "string"
            return {"type": json_type, "enum": list(args)}

    # list[X] → {"type": "array", "items": <schema for X>}
    if origin is list:
        args = typing.get_args(hint)
        if args:
            return {"type": "array", "items": _hint_to_json_schema(args[0])}
        return {"type": "array"}

    # dataclass → {"type": "object", "properties": {...}, "required": [...]}
    if dataclasses.is_dataclass(hint) and isinstance(hint, type):
        props: dict[str, Any] = {}
        req: list[str] = []
        for field in dataclasses.fields(hint):
            props[field.name] = _hint_to_json_schema(field.type)
            no_default = field.default is dataclasses.MISSING
            no_factory = field.default_factory is dataclasses.MISSING  # type: ignore[misc]
            if no_default and no_factory:
                req.append(field.name)
        return {"type": "object", "properties": props, "required": req}

    if hint is str:
        return {"type": "string"}
    if hint is int:
        return {"type": "integer"}
    if hint is float:
        return {"type": "number"}
    if hint is bool:
        return {"type": "boolean"}
    if hint is dict:
        return {"type": "object"}
    if hint is list:
        return {"type": "array"}

    return {"type": "string"}  # safe fallback


def _fn_to_tool_schema(fn: Callable) -> dict[str, Any]:
    """Convert a typed Python function to a Gemini FunctionDeclaration-compatible dict.

    Extracts name, description (from docstring body before ``Args:``), and
    parameters (from type hints + docstring ``Args:`` section) to produce
    the same format as the hand-written dicts above.

    The function name must end with ``_fn``; that suffix is stripped to
    derive the tool name (e.g. ``find_entities_fn`` → ``find_entities``).
    """
    # Exclude "return" from hints before the loop to avoid processing it
    hints = {k: v for k, v in typing.get_type_hints(fn).items() if k != "return"}
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""

    # Description = everything before "Args:"
    desc_parts = doc.split("Args:")
    description = desc_parts[0].strip()

    # Parse the "Args:" section for per-parameter descriptions.
    # A line is treated as a new parameter only when the text before the first
    # colon is a single valid Python identifier that matches a parameter name.
    # Any other colon-containing line is treated as a continuation of the
    # current parameter description (e.g. "Note: case-insensitive").
    param_descs: dict[str, str] = {}
    param_names = set(sig.parameters.keys())
    if len(desc_parts) > 1:
        current_pname: str | None = None
        for line in desc_parts[1].strip().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Check whether this line starts a new parameter entry:
            # the token before the first colon must be a plain identifier
            # that exists in the function's parameter list.
            if ":" in stripped:
                before_colon, after_colon = stripped.split(":", 1)
                before_colon = before_colon.strip()
                if before_colon.isidentifier() and before_colon in param_names:
                    current_pname = before_colon
                    param_descs[current_pname] = after_colon.strip()
                    continue
            # Continuation line (indented or no valid param name before colon)
            if current_pname is not None:
                param_descs[current_pname] += " " + stripped

    # Build JSON Schema properties and required list.
    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        hint = hints.get(pname)
        prop = _hint_to_json_schema(hint)
        if pname in param_descs:
            prop["description"] = param_descs[pname]
        properties[pname] = prop
        if param.default is inspect.Parameter.empty:
            required.append(pname)

    return {
        "name": fn.__name__.removesuffix("_fn"),
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _tools_as_schemas() -> list[dict[str, Any]]:
    """Generate tool schemas from the typed function definitions.

    Used for validation and future ADK migration. The dict-based
    definitions above remain canonical for now.
    """
    return [_fn_to_tool_schema(fn) for fn in QUERY_TOOL_FUNCTIONS + EDIT_TOOL_FUNCTIONS]
