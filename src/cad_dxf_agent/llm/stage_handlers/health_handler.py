"""Stage handler for the health check stage.

Wraps check_drawing_health() to provide drawing quality analysis
as a stage in the VALIDATE pipeline.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.core.health_checker import check_drawing_health
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.objective_schema import ObjectiveClassification


class HealthHandler:
    """Stage handler that produces a drawing health report."""

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Run health checks and return report data."""
        drawing_context = context.get("drawing_context")
        if drawing_context is None:
            return {
                "health_report": None,
                "summary": "No drawing context available for health check",
            }

        # Accept DrawingContext directly or reconstruct from dict
        if not isinstance(drawing_context, DrawingContext):
            drawing_context = DrawingContext(**drawing_context)

        report = check_drawing_health(drawing_context)

        return {
            "health_report": report.model_dump(),
            "health_score": report.score,
            "health_issues": [issue.model_dump() for issue in report.issues],
            "checks_run": report.checks_run,
            "summary": report.summary,
        }
