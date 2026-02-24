"""Deterministic planner — handles obvious operations without calling LLM.

Pattern-matches simple, unambiguous prompts like:
  - "delete entity {handle}"
  - "move {handle} by (dx, dy)"
  - "change text of {handle} to '{new_text}'"

Returns None when the prompt doesn't match any pattern (fall through to LLM).
"""

from __future__ import annotations

import logging
import re

from ..models.ops_schema import ChangeSet, EditOperation, OpType

logger = logging.getLogger(__name__)

# Patterns for deterministic operations
_DELETE_PATTERN = re.compile(
    r"delete\s+entity\s+([A-Fa-f0-9]+)",
    re.IGNORECASE,
)
_MOVE_PATTERN = re.compile(
    r"move\s+([A-Fa-f0-9]+)\s+by\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)",
    re.IGNORECASE,
)
_EDIT_TEXT_PATTERN = re.compile(
    r"change\s+text\s+of\s+([A-Fa-f0-9]+)\s+to\s+['\"](.+?)['\"]",
    re.IGNORECASE,
)


def deterministic_plan(prompt: str, drawing_context: dict) -> ChangeSet | None:
    """Try to produce a ChangeSet without calling the LLM.

    Returns a ChangeSet for obvious operations, or None if the prompt
    doesn't match any deterministic pattern.
    """
    # Collect known handles from the drawing context
    known_handles = {e["handle"] for e in drawing_context.get("entities", []) if "handle" in e}

    # Try delete pattern
    m = _DELETE_PATTERN.search(prompt)
    if m:
        handle = m.group(1).upper()
        if handle in known_handles:
            logger.info("Deterministic delete: handle=%s", handle)
            return ChangeSet(
                prompt=prompt,
                operations=[
                    EditOperation(
                        op_type=OpType.DELETE_ENTITY,
                        target_handle=handle,
                    )
                ],
                revision_label=f"Deterministic delete: {handle}",
            )

    # Try move pattern
    m = _MOVE_PATTERN.search(prompt)
    if m:
        handle = m.group(1).upper()
        dx = float(m.group(2))
        dy = float(m.group(3))
        if handle in known_handles:
            logger.info("Deterministic move: handle=%s dx=%.1f dy=%.1f", handle, dx, dy)
            return ChangeSet(
                prompt=prompt,
                operations=[
                    EditOperation(
                        op_type=OpType.MOVE_ENTITY,
                        target_handle=handle,
                        params={"dx": dx, "dy": dy},
                    )
                ],
                revision_label=f"Deterministic move: {handle}",
            )

    # Try edit text pattern
    m = _EDIT_TEXT_PATTERN.search(prompt)
    if m:
        handle = m.group(1).upper()
        new_text = m.group(2)
        if handle in known_handles:
            logger.info("Deterministic edit_text: handle=%s", handle)
            return ChangeSet(
                prompt=prompt,
                operations=[
                    EditOperation(
                        op_type=OpType.EDIT_TEXT,
                        target_handle=handle,
                        params={"new_text": new_text},
                    )
                ],
                revision_label=f"Deterministic edit_text: {handle}",
            )

    return None
