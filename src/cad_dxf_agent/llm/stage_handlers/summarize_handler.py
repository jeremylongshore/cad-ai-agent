"""Stage handler for the summarize stage.

Uses enriched context + zone detection to produce a structured
plain-English drawing summary suitable for non-CAD users.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.core.drawing_summarizer import summarize_drawing
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.objective_schema import ObjectiveClassification
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult


class SummarizeHandler:
    """Stage handler that produces plain-English drawing summaries."""

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Run drawing summarization and return structured summary."""
        drawing_context = context.get("drawing_context")
        if drawing_context is None:
            return {"summary": "No drawing context available for summary"}

        if not isinstance(drawing_context, DrawingContext):
            drawing_context = DrawingContext(**drawing_context)

        # Use pre-computed zones if available from upstream stage
        zones = context.get("zones")
        if zones is not None and not isinstance(zones, ZoneDetectionResult):
            zones = ZoneDetectionResult(**zones)

        result = summarize_drawing(drawing_context, zones=zones)

        return {
            "summary": result.headline,
            "plain_description": result.plain_description,
            "drawing_type": result.drawing_type,
            "entity_count": result.entity_count,
            "layer_count": result.layer_count,
            "total_area": result.total_area,
            "room_count": result.room_count,
            "rooms": [r.model_dump() for r in result.rooms],
            "key_features": result.key_features,
            "layer_breakdown": result.layer_breakdown,
        }
