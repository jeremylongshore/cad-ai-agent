"""Drawing health report schemas — structured quality analysis output.

Health checks are deterministic (no LLM). Each check produces zero or more
HealthIssue objects grounded in entity evidence. The HealthReport aggregates
all issues with a numeric score and severity breakdown.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .response_schema import EvidenceRef


class HealthSeverity(StrEnum):
    """Severity level for a health issue."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class HealthCategory(StrEnum):
    """Category of health check that found the issue."""

    GEOMETRY = "geometry"
    TEXT = "text"
    LAYER = "layer"
    DIMENSION = "dimension"
    ZONE = "zone"
    OVERLAP = "overlap"
    GENERAL = "general"


class HealthIssue(BaseModel):
    """A single quality issue found in a drawing."""

    severity: HealthSeverity
    category: HealthCategory
    title: str
    description: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    check_name: str = ""


class HealthReport(BaseModel):
    """Aggregated drawing health report."""

    score: float = Field(
        ge=0,
        le=100,
        description="Overall health score (100 = no issues, 0 = severely degraded)",
    )
    issues: list[HealthIssue] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    entity_count: int = 0
    layer_count: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == HealthSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == HealthSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == HealthSeverity.INFO)

    @property
    def summary(self) -> str:
        """One-line human-readable summary."""
        if not self.issues:
            return f"Drawing health: {self.score:.0f}/100 — no issues found"
        parts = []
        if self.critical_count:
            parts.append(f"{self.critical_count} critical")
        if self.warning_count:
            parts.append(f"{self.warning_count} warning")
        if self.info_count:
            parts.append(f"{self.info_count} info")
        return f"Drawing health: {self.score:.0f}/100 — {', '.join(parts)}"
