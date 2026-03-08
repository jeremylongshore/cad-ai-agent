"""Compliance validation models for regulation-aware drawing checks.

Represents configurable compliance profiles (ADA, IBC, custom) and
structured findings with entity-level evidence. Used by the compliance
rules engine for deterministic code checking.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ComplianceSeverity(StrEnum):
    """Severity of a compliance finding."""

    VIOLATION = "violation"
    WARNING = "warning"
    PASS = "pass"  # noqa: S105


class ComplianceCategory(StrEnum):
    """Category of a compliance rule."""

    ACCESSIBILITY = "accessibility"
    EGRESS = "egress"
    ROOM_SIZE = "room_size"
    CORRIDOR = "corridor"
    DOOR = "door"
    WINDOW = "window"
    GENERAL = "general"


class ComplianceFinding(BaseModel):
    """A single compliance check result with entity-level evidence."""

    rule_id: str
    category: ComplianceCategory
    severity: ComplianceSeverity
    title: str
    description: str
    code_reference: str | None = None
    zone_id: str | None = None
    entity_handles: list[str] = Field(default_factory=list)
    measured_value: float | None = None
    required_value: float | None = None
    unit: str | None = None


class ComplianceThresholds(BaseModel):
    """Configurable thresholds for a compliance profile.

    Values are in drawing units. The caller is responsible for
    converting real-world dimensions to match the drawing scale.
    Default values use common architectural scales where
    1 drawing unit = 1 inch.
    """

    min_door_width: float = 36.0
    min_hallway_width: float = 44.0
    min_residential_hallway_width: float = 36.0
    min_habitable_room_area: float = 70.0 * 144  # 70 sq ft in sq inches
    min_bathroom_area: float = 35.0 * 144  # 35 sq ft in sq inches
    min_bedroom_area: float = 70.0 * 144  # 70 sq ft in sq inches
    max_dead_end_corridor_length: float = 240.0  # 20 ft in inches
    min_egress_window_area: float = 5.7 * 144  # 5.7 sq ft in sq inches
    min_ceiling_height: float = 90.0  # 7.5 ft in inches (not measurable from 2D)


class ComplianceProfile(BaseModel):
    """A named set of compliance rules with configurable thresholds."""

    name: str
    description: str
    thresholds: ComplianceThresholds = Field(
        default_factory=ComplianceThresholds,
    )
    enabled_categories: list[ComplianceCategory] = Field(
        default_factory=lambda: list(ComplianceCategory),
    )


class ComplianceReport(BaseModel):
    """Aggregate result of compliance checking against a profile."""

    profile_name: str
    findings: list[ComplianceFinding] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    violation_count: int = 0
    warning_count: int = 0
    pass_count: int = 0
    zone_count: int = 0
    entity_count: int = 0

    @property
    def passed(self) -> bool:
        """True if no violations were found."""
        return self.violation_count == 0

    @property
    def score(self) -> int:
        """Compliance score 0-100. 100 = all checks passed."""
        total = self.violation_count + self.warning_count + self.pass_count
        if total == 0:
            return 0
        return round((self.pass_count / total) * 100)


# --- Built-in profiles ---

ADA_PROFILE = ComplianceProfile(
    name="ada",
    description="ADA accessibility compliance checks",
    thresholds=ComplianceThresholds(
        min_door_width=36.0,
        min_hallway_width=44.0,
    ),
    enabled_categories=[
        ComplianceCategory.ACCESSIBILITY,
        ComplianceCategory.DOOR,
        ComplianceCategory.CORRIDOR,
    ],
)

IBC_PROFILE = ComplianceProfile(
    name="ibc-2021",
    description="IBC 2021 building code compliance checks",
    thresholds=ComplianceThresholds(),
    enabled_categories=list(ComplianceCategory),
)

RESIDENTIAL_PROFILE = ComplianceProfile(
    name="residential",
    description="Residential building code compliance (IRC-based)",
    thresholds=ComplianceThresholds(
        min_door_width=32.0,
        min_hallway_width=36.0,
        min_residential_hallway_width=36.0,
        min_habitable_room_area=70.0 * 144,
    ),
    enabled_categories=list(ComplianceCategory),
)

BUILTIN_PROFILES: dict[str, ComplianceProfile] = {
    "ada": ADA_PROFILE,
    "ibc-2021": IBC_PROFILE,
    "residential": RESIDENTIAL_PROFILE,
}
