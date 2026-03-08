"""Stage handler for the analyze stage.

Wraps build_enriched_context() from semantic_model to provide
family-aware drawing analysis as the first stage in most pipelines.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.core.semantic_model import build_enriched_context
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.objective_schema import ObjectiveClassification


class AnalyzeHandler:
    """Stage handler that produces enriched drawing analysis."""

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Run enriched context building and return analysis data."""
        drawing_context = context.get("drawing_context")
        if drawing_context is None:
            return {
                "summary": "No drawing context available for analysis",
            }

        # Accept DrawingContext directly or reconstruct from dict
        if not isinstance(drawing_context, DrawingContext):
            drawing_context = DrawingContext(**drawing_context)

        enriched = build_enriched_context(drawing_context)

        return {
            "enriched_context": enriched,
            "document_family": enriched.get("document_family"),
            "primitives": enriched.get("primitives"),
            "summary": (
                f"Analyzed {enriched.get('entity_count', 0)} entities across "
                f"{len(enriched.get('layers', []))} layers"
            ),
        }
