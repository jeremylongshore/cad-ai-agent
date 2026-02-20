"""Prompt templates for LLM planner interactions."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a CAD editing planner. Given a drawing context and a user request,
return a JSON array of structured edit operations.

RULES:
- You may ONLY return operations of these types: move_entity, edit_text, delete_entity, add_block
- You must reference entities by their handle
- You must NEVER target entities on protected layers
- All coordinates are in drawing units
- Return ONLY valid JSON matching the operations schema

OPERATIONS SCHEMA:
{{
  "operations": [
    {{
      "op_type": "move_entity|edit_text|delete_entity|add_block",
      "target_handle": "entity handle string",
      "target_layer": "optional layer name",
      "params": {{}}
    }}
  ],
  "revision_label": "brief description of changes"
}}

PARAMS BY OP TYPE:
- move_entity: {{"dx": number, "dy": number}}
- edit_text: {{"new_text": "string"}}
- delete_entity: {{}}
- add_block: {{"block_name": "str", "insert_point": {{"x": n, "y": n}},
  "scale": n, "rotation": n}}
"""

USER_PROMPT_TEMPLATE = """Drawing context:
{drawing_context}

User request:
{user_prompt}

Return the operations JSON:"""


def format_planner_prompt(user_prompt: str, drawing_context_json: str) -> str:
    """Format the user prompt with drawing context for the LLM."""
    return USER_PROMPT_TEMPLATE.format(
        drawing_context=drawing_context_json,
        user_prompt=user_prompt,
    )
