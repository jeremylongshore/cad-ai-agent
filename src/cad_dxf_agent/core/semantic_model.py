"""Semantic model — builds context summaries for the LLM planner."""

from __future__ import annotations

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
