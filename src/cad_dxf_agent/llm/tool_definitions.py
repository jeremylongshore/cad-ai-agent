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

FIND_ENTITIES = {
    "name": "find_entities",
    "description": (
        "Search for entities in the drawing by layer, type, and/or text content. "
        "Returns a list of matching entities with handle, type, layer, position, and text."
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
                "description": "Filter by entity type: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT",
                "enum": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT", "INSERT"],
            },
            "text_contains": {
                "type": "string",
                "description": (
                    "Search for entities whose text contains this string (case-insensitive)"
                ),
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
        "at grid intersections or near specific coordinates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "x": {"type": "number", "description": "X coordinate in drawing units"},
            "y": {"type": "number", "description": "Y coordinate in drawing units"},
            "entity_type": {
                "type": "string",
                "description": "Optional type filter",
                "enum": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT", "INSERT"],
            },
            "layer": {
                "type": "string",
                "description": "Optional layer filter (case-insensitive)",
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
# Query tools (read-only) vs. edit tools (produce operations)
# ---------------------------------------------------------------------------

QUERY_TOOLS = [FIND_ENTITIES, GET_ENTITY, FIND_NEAREST, LIST_LAYERS, IS_PROTECTED]
EDIT_TOOLS = [MOVE_ENTITY, EDIT_TEXT, DELETE_ENTITY, ADD_BLOCK]
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
