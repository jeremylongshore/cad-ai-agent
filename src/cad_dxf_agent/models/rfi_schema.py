"""RFI (Request for Information) generation schemas.

Represents structured questions that contractors would ask about
ambiguous or incomplete drawing information. Each RFI item references
specific entities and locations for traceability.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RFISeverity(StrEnum):
    """How critical the information gap is."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class RFICategory(StrEnum):
    """Type of information gap."""

    MISSING_DIMENSION = "missing_dimension"
    AMBIGUOUS_SYMBOL = "ambiguous_symbol"
    MISSING_LABEL = "missing_label"
    INCOMPLETE_SECTION = "incomplete_section"
    COORDINATION = "coordination"
    GENERAL = "general"


class RFIItem(BaseModel):
    """A single RFI question with location and evidence."""

    rfi_id: str
    category: RFICategory
    severity: RFISeverity
    question: str
    location_description: str
    entity_handles: list[str] = Field(default_factory=list)
    zone_id: str | None = None
    suggested_resolution: str = ""


class RFIReport(BaseModel):
    """Aggregate RFI report from drawing analysis."""

    items: list[RFIItem] = Field(default_factory=list)
    total_items: int = 0
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    checks_run: list[str] = Field(default_factory=list)
    entity_count: int = 0
    zone_count: int = 0
