"""CAD tool definitions for Gemini function calling.

Defines the tool schemas that the LLM agent can invoke to query and
edit the drawing. Each tool wraps existing EntityIndex / EditEngine
methods. The LLM never touches DXF directly — it calls these tools,
and the host code executes them against the validated pipeline.
"""

from __future__ import annotations

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
