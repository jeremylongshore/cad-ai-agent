"""AI revision notes — deterministic note generation from applied operations."""

from __future__ import annotations

import logging
from pathlib import Path

import ezdxf

from ..models.config_schema import RevisionNoteConfig
from ..models.ops_schema import AppliedChange, OpType
from ..otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def generate_note_text(
    changes: list[AppliedChange],
    config: RevisionNoteConfig,
) -> str:
    """Generate deterministic revision note text from applied changes.

    Never uses LLM output — text is built from operation metadata.
    """
    prefix = f"{config.prefix} {config.revision_number}"

    if not changes:
        return f"{prefix} - No changes applied"

    successful = [c for c in changes if c.success]
    if not successful:
        return f"{prefix} - No successful changes"

    summaries = []
    for change in successful:
        summary = _summarize_change(change)
        if summary:
            summaries.append(summary)

    if not summaries:
        return f"{prefix} - {len(successful)} operation(s) applied"

    if len(summaries) == 1:
        return f"{prefix} - {summaries[0]}"

    # Multiple changes: combine concisely
    return f"{prefix} - {'; '.join(summaries)}"


def insert_revision_note(
    dxf_path: str | Path,
    output_path: str | Path,
    changes: list[AppliedChange],
    config: RevisionNoteConfig,
    *,
    layout_name: str = "Model",
) -> str:
    """Insert a revision note into a DXF file on the dedicated AI_REV_NOTES layer.

    Operates on an already-edited DXF (post-apply). Saves to output_path.
    When ``layout_name`` is provided and is not "Model", the note is inserted
    into the named paper space layout instead of model space.
    Returns the note text that was inserted.
    """
    with tracer.start_as_current_span("cad.revision_note") as span:
        span.set_attribute("cad.revision.layer", config.layer_name)
        span.set_attribute("cad.revision.layout", layout_name)

        doc = ezdxf.readfile(str(dxf_path))

        # Resolve target layout (BaseLayout is the common type for both)
        target: ezdxf.layouts.BaseLayout
        if layout_name == "Model":
            target = doc.modelspace()
        else:
            try:
                target = doc.layouts.get(layout_name)
            except KeyError:
                logger.warning(
                    "Layout %r not found, falling back to model space",
                    layout_name,
                )
                target = doc.modelspace()

        # Ensure the notes layer exists
        if config.layer_name not in doc.layers:
            doc.layers.add(config.layer_name, color=7)

        note_text = generate_note_text(changes, config)

        target.add_mtext(
            note_text,
            dxfattribs={
                "layer": config.layer_name,
                "insert": (config.anchor_point.x, config.anchor_point.y),
                "char_height": config.text_height,
            },
        )

        doc.saveas(str(output_path))
        logger.info(
            "Inserted revision note on layer %s in %s: %s",
            config.layer_name,
            layout_name,
            note_text,
        )
        return note_text


def _summarize_change(change: AppliedChange) -> str:
    """Generate a concise summary for a single applied change."""
    op = change.operation

    if op.op_type == OpType.MOVE_ENTITY:
        dx = op.params.get("dx", 0)
        dy = op.params.get("dy", 0)
        direction = _describe_direction(dx, dy)
        distance = _format_distance(dx, dy)
        return f"Moved entity {direction} {distance}"

    elif op.op_type == OpType.EDIT_TEXT:
        new_text = op.params.get("new_text", "")
        truncated = new_text[:30] + "..." if len(new_text) > 30 else new_text
        return f"Updated text to '{truncated}'"

    elif op.op_type == OpType.DELETE_ENTITY:
        return "Deleted entity"

    elif op.op_type == OpType.ADD_BLOCK:
        block_name = op.params.get("block_name", "unknown")
        return f"Inserted block {block_name}"

    return ""


def _describe_direction(dx: float, dy: float) -> str:
    """Describe movement direction in cardinal terms."""
    parts = []
    if abs(dy) > 0.001:
        parts.append("north" if dy > 0 else "south")
    if abs(dx) > 0.001:
        parts.append("east" if dx > 0 else "west")
    return "-".join(parts) if parts else ""


def _format_distance(dx: float, dy: float) -> str:
    """Format distance as engineering-friendly string."""
    import math

    dist = math.sqrt(dx**2 + dy**2)
    if dist < 12:
        return f'{dist:.1f}"'
    feet = int(dist // 12)
    inches = dist % 12
    return f"{feet}'-{inches:.0f}\""
