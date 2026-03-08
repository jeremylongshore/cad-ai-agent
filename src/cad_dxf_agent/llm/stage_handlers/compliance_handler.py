"""Stage handler for regulation-aware compliance validation.

Wraps check_compliance() to provide building code validation
as a stage in the VALIDATE pipeline.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.core.compliance_rules import check_compliance
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.compliance_schema import BUILTIN_PROFILES
from cad_dxf_agent.models.objective_schema import ObjectiveClassification
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult


class ComplianceHandler:
    """Stage handler that produces a compliance report against a profile."""

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Run compliance checks and return report data."""
        drawing_context = context.get("drawing_context")
        if drawing_context is None:
            return {
                "compliance_report": None,
                "summary": "No drawing context available for compliance check",
            }

        if not isinstance(drawing_context, DrawingContext):
            drawing_context = DrawingContext(**drawing_context)

        # Use pre-computed zones from prior stage if available
        zones = None
        raw_zones = context.get("zones")
        if raw_zones is not None:
            if isinstance(raw_zones, ZoneDetectionResult):
                zones = raw_zones
            elif isinstance(raw_zones, list):
                zones = ZoneDetectionResult(
                    zones=raw_zones,
                    total_area=context.get("total_area", 0.0),
                    zone_count=context.get("zone_count", 0),
                    confidence=context.get("zone_confidence", 0.0),
                    warnings=context.get("zone_warnings", []),
                )

        # Determine profile from prompt keywords or default to "ibc"
        profile = _detect_profile(prompt)

        report = check_compliance(drawing_context, profile=profile, zones=zones)

        return {
            "compliance_report": report.model_dump(),
            "compliance_profile": report.profile_name,
            "compliance_score": report.score,
            "compliance_passed": report.passed,
            "compliance_findings": [f.model_dump() for f in report.findings],
            "compliance_violations": report.violation_count,
            "compliance_warnings": report.warning_count,
            "compliance_checks_run": report.checks_run,
            "summary": _build_summary(report),
        }


def _detect_profile(prompt: str) -> str:
    """Detect compliance profile from prompt keywords."""
    lower = prompt.lower()
    if "ada" in lower or "accessib" in lower:
        return "ada"
    if "residential" in lower or "irc" in lower:
        return "residential"
    # Default to IBC-2021 (most comprehensive)
    return "ibc-2021"


def _build_summary(report) -> str:
    """Build a human-readable summary of compliance results."""
    status = "PASSED" if report.passed else f"FAILED — {report.violation_count} violation(s)"
    warnings = f" with {report.warning_count} warning(s)" if report.warning_count else ""
    score = f". Score: {report.score:.0f}/100."
    return f"Compliance check ({report.profile_name}): {status}{warnings}{score}"
