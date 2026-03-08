"""Stage handler for zone/room detection.

Wraps the deterministic zone detector to plug into the stage pipeline executor.
Runs detect_zones() on a DrawingContext rebuilt from the accumulated context dict.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.objective_schema import ObjectiveClassification


class DetectZonesHandler:
    """Stage handler that detects enclosed zones/rooms in the drawing."""

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Run zone detection and return results for downstream stages."""
        drawing_context = context.get("drawing_context")
        if drawing_context is None:
            return {
                "zones": [],
                "zone_count": 0,
                "total_area": 0.0,
                "summary": "No drawing context available for zone detection",
            }

        # Accept DrawingContext directly or reconstruct from dict
        if not isinstance(drawing_context, DrawingContext):
            drawing_context = DrawingContext(**drawing_context)

        result = detect_zones(drawing_context)

        zone_dicts = [z.model_dump() for z in result.zones]

        # Build human-readable summary
        if result.zone_count == 0:
            summary = "No enclosed zones detected in the drawing."
        elif result.zone_count == 1:
            z = result.zones[0]
            summary = f"1 zone detected: {z.inferred_type or 'unknown'} ({z.area:.1f} sq units)"
        else:
            type_counts: dict[str, int] = {}
            for z in result.zones:
                t = z.inferred_type or "unknown"
                type_counts[t] = type_counts.get(t, 0) + 1
            type_desc = ", ".join(f"{v} {k}" for k, v in type_counts.items())
            summary = (
                f"{result.zone_count} zones detected ({type_desc}), "
                f"total area: {result.total_area:.1f} sq units"
            )

        return {
            "zones": zone_dicts,
            "zone_count": result.zone_count,
            "total_area": result.total_area,
            "zone_confidence": result.confidence,
            "zone_method": result.method,
            "zone_warnings": result.warnings,
            "summary": summary,
        }
