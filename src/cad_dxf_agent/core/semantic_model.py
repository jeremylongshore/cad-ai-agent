"""Semantic model — builds context summaries for the LLM planner."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..models.cad_schema import DrawingContext
from ..otel import get_tracer

tracer = get_tracer(__name__)


def build_planner_context(context: DrawingContext) -> dict:
    """Build a JSON-serializable summary of the drawing for the LLM planner.

    This is the information the planner sees to make targeting decisions.
    It does NOT include raw DXF data. Includes all spaces (model + layouts).
    """
    with tracer.start_as_current_span("cad.build_context") as span:
        span.set_attribute("cad.entities.count", context.entity_count)

        layer_summary = [
            {
                "name": layer.name,
                "protected": layer.protected,
                "entity_count": sum(
                    1 for e in context.entities if e.layer.upper() == layer.name.upper()
                ),
            }
            for layer in context.layers
        ]

        entity_summary = [
            {
                "handle": e.handle,
                "type": e.entity_type.value,
                "layer": e.layer,
                "space": e.space,
                "insert_point": (
                    {"x": e.insert_point.x, "y": e.insert_point.y} if e.insert_point else None
                ),
                "text": e.text_content,
                "block_name": e.block_name,
            }
            for e in context.entities
        ]

        layout_summary = [
            {"name": layout.name, "entity_count": layout.entity_count} for layout in context.layouts
        ]

        return {
            "file_path": context.file_path,
            "entity_count": context.entity_count,
            "layers": layer_summary,
            "entities": entity_summary,
            "blocks": context.blocks,
            "layouts": layout_summary,
            "unsupported_types": context.unsupported_entity_types,
        }


def build_compact_context(context: DrawingContext) -> str:
    """Build a compact text summary for the LLM agent's initial prompt.

    Instead of dumping all entity JSON, provides a high-level overview
    so the agent uses query tools (find_entities, find_nearest) to
    discover specific entities before acting.
    """
    counts_by_layer: Counter[str] = Counter()
    counts_by_type: Counter[str] = Counter()
    text_labels: list[str] = []

    for entity in context.entities:
        counts_by_layer[entity.layer] += 1
        counts_by_type[entity.entity_type.value] += 1
        if entity.text_content:
            text_labels.append(entity.text_content)

    protected = context.get_protected_layers()

    lines = [
        "DRAWING SUMMARY:",
        f"- File: {Path(context.file_path).name}",
        f"- Total entities: {context.entity_count}",
        f"- Entity types: {', '.join(f'{t}({n})' for t, n in counts_by_type.most_common())}",
        "- Layers:",
    ]

    for layer in context.layers:
        count = counts_by_layer.get(layer.name, 0)
        prot = " (PROTECTED)" if layer.name in protected else ""
        lines.append(f"    {layer.name}: {count} entities{prot}")

    if context.blocks:
        lines.append(f"- Blocks available: {', '.join(context.blocks)}")

    if context.layouts:
        layout_desc = ", ".join(f"{lay.name}({lay.entity_count})" for lay in context.layouts)
        lines.append(f"- Layouts: {layout_desc}")

    if text_labels:
        sample = text_labels[:5]
        lines.append(f"- Sample text labels: {sample}")

    lines.append("")
    lines.append(
        "Use find_entities(), get_entity(), find_nearest() tools to query specific entities."
    )
    lines.append("Do NOT guess entity handles — always search first.")

    return "\n".join(lines)
