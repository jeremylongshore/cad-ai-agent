"""Compliance rules engine — deterministic regulation-aware validation.

Checks drawings against configurable compliance profiles (ADA, IBC, custom).
Each rule function is deterministic (no LLM) and returns entity-level evidence.

Rules use zone detection for room analysis and entity index for door/window
detection via INSERT block names.

Public API:
    check_compliance(context, profile="ada") -> ComplianceReport
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType
from cad_dxf_agent.models.compliance_schema import (
    BUILTIN_PROFILES,
    ComplianceCategory,
    ComplianceFinding,
    ComplianceProfile,
    ComplianceReport,
    ComplianceSeverity,
    ComplianceThresholds,
)
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

logger = logging.getLogger(__name__)

_CheckFn = Callable[
    [DrawingContext, ZoneDetectionResult, EntityIndex, ComplianceThresholds],
    list[ComplianceFinding],
]

# --- Block name patterns for door/window detection ---
_DOOR_PATTERNS = re.compile(
    r"door|dr[_\-\s]|entry|exit|gate|swing",
    re.IGNORECASE,
)
_WINDOW_PATTERNS = re.compile(
    r"window|wndw|win[_\-\s]|glazing|glass",
    re.IGNORECASE,
)


def check_compliance(
    context: DrawingContext,
    profile: str | ComplianceProfile = "ada",
    *,
    zones: ZoneDetectionResult | None = None,
) -> ComplianceReport:
    """Run compliance checks against a profile.

    Args:
        context: Drawing context with entities.
        profile: Profile name (string) or ComplianceProfile object.
        zones: Pre-computed zone detection result (computed if None).

    Returns:
        ComplianceReport with categorized findings and score.
    """
    if isinstance(profile, str):
        prof = BUILTIN_PROFILES.get(profile)
        if prof is None:
            raise ValueError(
                f"Unknown profile: {profile}. "
                f"Available: {', '.join(BUILTIN_PROFILES)}"
            )
    else:
        prof = profile

    if zones is None:
        zones = detect_zones(context)

    index = EntityIndex(context)
    findings: list[ComplianceFinding] = []
    checks_run: list[str] = []

    enabled = set(prof.enabled_categories)
    thresholds = prof.thresholds

    # Run each check if its category is enabled
    for check_fn, category, check_name in _ALL_CHECKS:
        if category in enabled:
            checks_run.append(check_name)
            results = check_fn(context, zones, index, thresholds)
            findings.extend(results)

    violation_count = sum(
        1 for f in findings if f.severity == ComplianceSeverity.VIOLATION
    )
    warning_count = sum(
        1 for f in findings if f.severity == ComplianceSeverity.WARNING
    )
    pass_count = sum(
        1 for f in findings if f.severity == ComplianceSeverity.PASS
    )

    return ComplianceReport(
        profile_name=prof.name,
        findings=findings,
        checks_run=checks_run,
        violation_count=violation_count,
        warning_count=warning_count,
        pass_count=pass_count,
        zone_count=zones.zone_count,
        entity_count=context.entity_count,
    )


# --- Individual check functions ---


def _check_door_widths(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check door block widths against minimum requirements.

    Detects doors from INSERT blocks with door-related names.
    Width is estimated from block attributes or nearby dimension text.
    """
    findings: list[ComplianceFinding] = []
    doors = _find_blocks_by_pattern(context, _DOOR_PATTERNS)

    if not doors:
        return findings

    for entity in doors:
        # Try to get door width from block attributes
        width = _extract_dimension_from_attributes(entity.attributes)

        if width is not None and width < thresholds.min_door_width:
            findings.append(ComplianceFinding(
                rule_id="DOOR-WIDTH-001",
                category=ComplianceCategory.DOOR,
                severity=ComplianceSeverity.VIOLATION,
                title="Door width below minimum",
                description=(
                    f"Door '{entity.block_name}' has width {width:.1f} "
                    f"but minimum is {thresholds.min_door_width:.1f}"
                ),
                code_reference="ADA 404.2.3 / IBC 1010.1.1",
                entity_handles=[entity.handle],
                measured_value=width,
                required_value=thresholds.min_door_width,
                unit="drawing_units",
            ))
        elif width is not None and width >= thresholds.min_door_width:
            findings.append(ComplianceFinding(
                rule_id="DOOR-WIDTH-001",
                category=ComplianceCategory.DOOR,
                severity=ComplianceSeverity.PASS,
                title="Door width meets minimum",
                description=(
                    f"Door '{entity.block_name}' width {width:.1f} "
                    f"meets minimum {thresholds.min_door_width:.1f}"
                ),
                entity_handles=[entity.handle],
                measured_value=width,
                required_value=thresholds.min_door_width,
                unit="drawing_units",
            ))

    return findings


def _check_hallway_widths(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check hallway/corridor zones against minimum width requirements.

    Uses zone detection to find hallway-classified zones and checks
    their minimum bounding-box dimension as a width proxy.
    """
    findings: list[ComplianceFinding] = []

    hallways = [
        z for z in zones.zones
        if z.inferred_type in ("hallway", "corridor")
    ]

    for zone in hallways:
        min_dim = _zone_min_dimension(zone)
        if min_dim < thresholds.min_hallway_width:
            findings.append(ComplianceFinding(
                rule_id="CORRIDOR-WIDTH-001",
                category=ComplianceCategory.CORRIDOR,
                severity=ComplianceSeverity.VIOLATION,
                title="Corridor width below minimum",
                description=(
                    f"Corridor (zone {zone.zone_id[:8]}) has width "
                    f"{min_dim:.1f} but minimum is "
                    f"{thresholds.min_hallway_width:.1f}"
                ),
                code_reference="IBC 1020.2 / ADA 403.5.1",
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
                measured_value=min_dim,
                required_value=thresholds.min_hallway_width,
                unit="drawing_units",
            ))
        else:
            findings.append(ComplianceFinding(
                rule_id="CORRIDOR-WIDTH-001",
                category=ComplianceCategory.CORRIDOR,
                severity=ComplianceSeverity.PASS,
                title="Corridor width meets minimum",
                description=(
                    f"Corridor (zone {zone.zone_id[:8]}) width "
                    f"{min_dim:.1f} meets minimum "
                    f"{thresholds.min_hallway_width:.1f}"
                ),
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
                measured_value=min_dim,
                required_value=thresholds.min_hallway_width,
                unit="drawing_units",
            ))

    return findings


def _check_room_areas(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check habitable room zones against minimum area requirements.

    Maps inferred zone types to minimum area thresholds from the profile.
    """
    findings: list[ComplianceFinding] = []

    habitable_types = {
        "bedroom", "living_room", "family_room", "dining_room",
        "kitchen", "office", "room", "large_room",
    }
    bathroom_types = {"bathroom"}

    for zone in zones.zones:
        if zone.inferred_type in habitable_types:
            min_area = thresholds.min_habitable_room_area
            if zone.inferred_type == "bedroom":
                min_area = thresholds.min_bedroom_area

            if zone.area < min_area:
                findings.append(ComplianceFinding(
                    rule_id="ROOM-AREA-001",
                    category=ComplianceCategory.ROOM_SIZE,
                    severity=ComplianceSeverity.VIOLATION,
                    title=f"{zone.inferred_type.replace('_', ' ').title()} "
                          f"area below minimum",
                    description=(
                        f"Zone {zone.zone_id[:8]} "
                        f"({zone.inferred_type}) has area {zone.area:.1f} "
                        f"but minimum is {min_area:.1f}"
                    ),
                    code_reference="IBC 1208.1 / IRC R304.1",
                    zone_id=zone.zone_id,
                    entity_handles=zone.source_handles,
                    measured_value=zone.area,
                    required_value=min_area,
                    unit="drawing_units²",
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="ROOM-AREA-001",
                    category=ComplianceCategory.ROOM_SIZE,
                    severity=ComplianceSeverity.PASS,
                    title=f"{zone.inferred_type.replace('_', ' ').title()} "
                          f"area meets minimum",
                    description=(
                        f"Zone {zone.zone_id[:8]} "
                        f"({zone.inferred_type}) area {zone.area:.1f} "
                        f"meets minimum {min_area:.1f}"
                    ),
                    zone_id=zone.zone_id,
                    entity_handles=zone.source_handles,
                    measured_value=zone.area,
                    required_value=min_area,
                    unit="drawing_units²",
                ))

        elif zone.inferred_type in bathroom_types:
            min_area = thresholds.min_bathroom_area
            if zone.area < min_area:
                findings.append(ComplianceFinding(
                    rule_id="ROOM-AREA-002",
                    category=ComplianceCategory.ROOM_SIZE,
                    severity=ComplianceSeverity.WARNING,
                    title="Bathroom area below recommended minimum",
                    description=(
                        f"Zone {zone.zone_id[:8]} (bathroom) has area "
                        f"{zone.area:.1f} but recommended minimum is "
                        f"{min_area:.1f}"
                    ),
                    code_reference="IRC R304",
                    zone_id=zone.zone_id,
                    entity_handles=zone.source_handles,
                    measured_value=zone.area,
                    required_value=min_area,
                    unit="drawing_units²",
                ))

    return findings


def _check_egress(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check that habitable rooms have egress (door or window nearby).

    For each habitable zone, searches for door/window blocks within
    a radius proportional to the zone's perimeter.
    """
    findings: list[ComplianceFinding] = []

    habitable_types = {
        "bedroom", "living_room", "family_room", "dining_room",
        "kitchen", "office", "room", "large_room",
    }

    doors = _find_blocks_by_pattern(context, _DOOR_PATTERNS)
    windows = _find_blocks_by_pattern(context, _WINDOW_PATTERNS)
    egress_entities = doors + windows

    for zone in zones.zones:
        if zone.inferred_type not in habitable_types:
            continue

        # Search radius: proportional to zone size
        search_radius = max(zone.perimeter * 0.3, 50.0)
        has_egress = False

        for entity in egress_entities:
            if entity.insert_point is None:
                continue
            dx = entity.insert_point.x - zone.centroid.x
            dy = entity.insert_point.y - zone.centroid.y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= search_radius:
                has_egress = True
                break

        if not has_egress:
            findings.append(ComplianceFinding(
                rule_id="EGRESS-001",
                category=ComplianceCategory.EGRESS,
                severity=ComplianceSeverity.WARNING,
                title="Room may lack egress",
                description=(
                    f"Zone {zone.zone_id[:8]} "
                    f"({zone.inferred_type}) has no door or window "
                    f"detected within {search_radius:.0f} units of "
                    f"its centroid"
                ),
                code_reference="IBC 1030.1 / IRC R310.1",
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
            ))
        else:
            findings.append(ComplianceFinding(
                rule_id="EGRESS-001",
                category=ComplianceCategory.EGRESS,
                severity=ComplianceSeverity.PASS,
                title="Room has egress",
                description=(
                    f"Zone {zone.zone_id[:8]} "
                    f"({zone.inferred_type}) has door/window "
                    f"within {search_radius:.0f} units"
                ),
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
            ))

    return findings


def _check_door_count(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check that the drawing has at least one exit door.

    A drawing with rooms but no detected door blocks is a compliance warning.
    """
    findings: list[ComplianceFinding] = []

    if zones.zone_count == 0:
        return findings

    doors = _find_blocks_by_pattern(context, _DOOR_PATTERNS)
    if not doors:
        findings.append(ComplianceFinding(
            rule_id="DOOR-COUNT-001",
            category=ComplianceCategory.DOOR,
            severity=ComplianceSeverity.WARNING,
            title="No doors detected in drawing",
            description=(
                "Drawing has rooms but no door blocks detected. "
                "Verify door symbols use standard block names "
                "(DOOR, DR-, ENTRY, EXIT)."
            ),
            code_reference="IBC 1010.1",
        ))
    else:
        findings.append(ComplianceFinding(
            rule_id="DOOR-COUNT-001",
            category=ComplianceCategory.DOOR,
            severity=ComplianceSeverity.PASS,
            title=f"{len(doors)} door(s) detected",
            description=f"Drawing has {len(doors)} door block(s).",
            entity_handles=[d.handle for d in doors[:10]],
        ))

    return findings


def _check_dead_end_corridors(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    index: EntityIndex,
    thresholds: ComplianceThresholds,
) -> list[ComplianceFinding]:
    """Check corridor zones for excessive length (dead-end risk).

    Uses the max bounding-box dimension as a length proxy.
    """
    findings: list[ComplianceFinding] = []

    hallways = [
        z for z in zones.zones
        if z.inferred_type in ("hallway", "corridor")
    ]

    for zone in hallways:
        max_dim = _zone_max_dimension(zone)
        if max_dim > thresholds.max_dead_end_corridor_length:
            findings.append(ComplianceFinding(
                rule_id="CORRIDOR-LENGTH-001",
                category=ComplianceCategory.CORRIDOR,
                severity=ComplianceSeverity.WARNING,
                title="Corridor may exceed dead-end limit",
                description=(
                    f"Corridor (zone {zone.zone_id[:8]}) has length "
                    f"{max_dim:.1f} which exceeds dead-end limit of "
                    f"{thresholds.max_dead_end_corridor_length:.1f}"
                ),
                code_reference="IBC 1020.4",
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
                measured_value=max_dim,
                required_value=thresholds.max_dead_end_corridor_length,
                unit="drawing_units",
            ))

    return findings


# --- Check registry ---

# Check registry: list of (function, category, name) tuples
_ALL_CHECKS: list[tuple[_CheckFn, ComplianceCategory, str]] = [
    (_check_door_widths, ComplianceCategory.DOOR, "door_widths"),
    (_check_door_count, ComplianceCategory.DOOR, "door_count"),
    (_check_hallway_widths, ComplianceCategory.CORRIDOR, "hallway_widths"),
    (_check_dead_end_corridors, ComplianceCategory.CORRIDOR, "dead_end_corridors"),
    (_check_room_areas, ComplianceCategory.ROOM_SIZE, "room_areas"),
    (_check_egress, ComplianceCategory.EGRESS, "egress"),
]


# --- Helper functions ---


def _find_blocks_by_pattern(context: DrawingContext, pattern: re.Pattern) -> list:
    """Find INSERT entities whose block_name matches a regex pattern."""
    results = []
    for entity in context.entities:
        if entity.entity_type != EntityType.INSERT:
            continue
        if entity.block_name and pattern.search(entity.block_name):
            results.append(entity)
    return results


def _extract_dimension_from_attributes(
    attributes: dict,
) -> float | None:
    """Try to extract a width/dimension from block attributes.

    Looks for common attribute keys like 'width', 'w', 'size'.
    """
    for key in ("width", "w", "WIDTH", "W", "size", "SIZE", "opening"):
        if key in attributes:
            try:
                return float(attributes[key])
            except (TypeError, ValueError):
                continue

    # Check x_scale as a width proxy (common for parameterized door blocks)
    if "x_scale" in attributes:
        try:
            return abs(float(attributes["x_scale"]))
        except (TypeError, ValueError):
            pass

    return None


def _zone_min_dimension(zone: DetectedZone) -> float:
    """Get the minimum bounding-box dimension of a zone."""
    if len(zone.boundary) < 2:
        return 0.0
    xs = [v.x for v in zone.boundary]
    ys = [v.y for v in zone.boundary]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return min(width, height) if width > 0 and height > 0 else 0.0


def _zone_max_dimension(zone: DetectedZone) -> float:
    """Get the maximum bounding-box dimension of a zone."""
    if len(zone.boundary) < 2:
        return 0.0
    xs = [v.x for v in zone.boundary]
    ys = [v.y for v in zone.boundary]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return max(width, height)
