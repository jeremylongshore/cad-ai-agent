"""Drawing health checker — deterministic quality analysis.

A collection of checks that analyze a DrawingContext for common drawing
quality issues: unclosed polylines, inconsistent text heights, orphan
layers, overlapping entities, unnamed zones, and missing dimensions.

Every check is deterministic (no LLM), evidence-grounded (references
specific entities), and self-contained. The checker aggregates all
results into a HealthReport with a numeric score.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from ..models.cad_schema import DrawingContext, EntityType
from ..models.health_schema import (
    HealthCategory,
    HealthIssue,
    HealthReport,
    HealthSeverity,
)
from ..models.response_schema import EvidenceRef
from ..otel import get_tracer
from .entity_index import EntityIndex

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_drawing_health(
    context: DrawingContext,
    *,
    include_zones: bool = True,
) -> HealthReport:
    """Run all health checks and return an aggregated report.

    Args:
        context: The DrawingContext to analyze
        include_zones: Whether to run zone-dependent checks (requires zone_detector)

    Returns:
        HealthReport with score, issues, and metadata
    """
    with tracer.start_as_current_span("cad.health_check") as span:
        span.set_attribute("cad.entities.count", context.entity_count)

        issues: list[HealthIssue] = []
        checks_run: list[str] = []
        index = EntityIndex(context)

        # Run each check
        for check_fn in _ALL_CHECKS:
            check_name = check_fn.__name__
            checks_run.append(check_name)
            try:
                found = check_fn(context, index)
                issues.extend(found)
            except Exception:
                logger.exception("Health check %s failed", check_name)

        # Zone-dependent checks
        if include_zones:
            try:
                zone_issues = _check_unnamed_zones(context)
                issues.extend(zone_issues)
                checks_run.append("check_unnamed_zones")
            except Exception:
                logger.exception("Zone health check failed")

        # Compute score
        score = _compute_score(issues, context.entity_count)

        span.set_attribute("cad.health.score", score)
        span.set_attribute("cad.health.issue_count", len(issues))

        return HealthReport(
            score=score,
            issues=issues,
            checks_run=checks_run,
            entity_count=context.entity_count,
            layer_count=len(context.layers),
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_polylines_missing_geometry(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag LWPOLYLINE entities missing position/vertex data.

    Identifies polylines that lack insert_point data, which prevents
    automated geometry analysis (closure, area calculation, etc.).
    These entities may need manual inspection.
    """
    issues = []
    polylines = index.get_by_type(EntityType.LWPOLYLINE)

    for entity in polylines:
        # We can only check if the entity has geometry info
        # For the DrawingContext model, polylines store vertices in raw_data
        if entity.insert_point is None:
            continue

        # Flag polylines with very small area relative to perimeter
        # (degenerate or near-degenerate geometry)
        # This is a simplified check — full check would need vertex data

    # For now, report polyline count as informational
    if len(polylines) > 0:
        # Check for polylines that lack proper vertex data
        no_position = [p for p in polylines if p.insert_point is None]
        if no_position:
            issues.append(
                HealthIssue(
                    severity=HealthSeverity.INFO,
                    category=HealthCategory.GEOMETRY,
                    title="Polylines without position data",
                    description=(
                        f"{len(no_position)} polyline(s) have no insert_point — "
                        "they may need manual inspection for closure"
                    ),
                    evidence=[
                        EvidenceRef(
                            entity_handle=e.handle,
                            layer=e.layer,
                            description="Polyline without position data",
                        )
                        for e in no_position[:5]
                    ],
                    check_name="check_polylines_missing_geometry",
                )
            )

    return issues


def _check_inconsistent_text_heights(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag layers where TEXT/MTEXT entities have inconsistent heights.

    When a layer has text at multiple different heights, it may indicate
    a standards violation or accidental scaling.
    """
    issues = []

    # Group text entities by layer, collect heights
    layer_heights: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for entity in context.entities:
        if entity.entity_type not in (EntityType.TEXT, EntityType.MTEXT):
            continue
        if entity.text_geometry is None:
            continue

        height = entity.text_geometry.effective_height
        if height is not None and height > 0:
            layer_heights[entity.layer].append((entity.handle, height))

    for layer, entries in layer_heights.items():
        if len(entries) < 2:
            continue

        heights = [h for _, h in entries]
        unique_heights = set(round(h, 2) for h in heights)

        if len(unique_heights) > 2:
            # More than 2 distinct heights on one layer = likely inconsistency
            height_counts = Counter(round(h, 2) for h in heights)
            dominant = height_counts.most_common(1)[0]
            outliers = [(handle, h) for handle, h in entries if round(h, 2) != dominant[0]]

            issues.append(
                HealthIssue(
                    severity=HealthSeverity.WARNING,
                    category=HealthCategory.TEXT,
                    title=f"Inconsistent text heights on layer {layer}",
                    description=(
                        f"{len(unique_heights)} different text heights found on layer "
                        f"'{layer}'. Dominant height: {dominant[0]}, "
                        f"{len(outliers)} outlier(s)."
                    ),
                    evidence=[
                        EvidenceRef(
                            entity_handle=handle,
                            layer=layer,
                            description=f"Text height {h:.2f} (expected {dominant[0]})",
                        )
                        for handle, h in outliers[:5]
                    ],
                    check_name="check_inconsistent_text_heights",
                )
            )

    return issues


def _check_orphan_layers(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag layers that are defined but have zero entities.

    Orphan layers add clutter and may indicate incomplete cleanup
    after drawing revisions.
    """
    issues = []
    orphans = []

    # Standard/system layers to exclude from orphan check
    system_layers = {"0", "DEFPOINTS"}

    for layer in context.layers:
        if layer.name.upper() in system_layers:
            continue
        entity_count = len(index.get_by_layer(layer.name))
        if entity_count == 0:
            orphans.append(layer.name)

    if orphans:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title=f"{len(orphans)} orphan layer(s) with no entities",
                description=(
                    f"Layers defined but containing no entities: "
                    f"{', '.join(orphans[:10])}"
                    f"{' (and more)' if len(orphans) > 10 else ''}"
                ),
                evidence=[
                    EvidenceRef(
                        layer=name,
                        description="Empty layer — no entities assigned",
                    )
                    for name in orphans[:10]
                ],
                check_name="check_orphan_layers",
            )
        )

    return issues


def _check_overlapping_entities(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag entities at identical coordinates (potential duplicates).

    Uses the R-tree spatial index for efficient proximity queries.
    For each entity, queries nearby entities within 0.01 drawing units
    on the same layer and flags groups as potential overlaps.
    """
    issues = []
    overlap_threshold = 0.01
    checked: set[str] = set()
    overlap_groups: dict[str, list[str]] = {}

    for entity in context.entities:
        if entity.insert_point is None or entity.handle in checked:
            continue
        checked.add(entity.handle)

        # Use R-tree to find nearby entities efficiently
        nearby = index.find_in_radius(
            entity.insert_point.x,
            entity.insert_point.y,
            overlap_threshold,
        )
        # Filter to same-layer neighbors (excluding self)
        same_layer = [n for n in nearby if n.handle != entity.handle and n.layer == entity.layer]
        if same_layer:
            key = f"{entity.insert_point.x:.2f},{entity.insert_point.y:.2f},{entity.layer}"
            handles = [entity.handle] + [n.handle for n in same_layer]
            overlap_groups[key] = handles
            checked.update(n.handle for n in same_layer)

    if overlap_groups:
        total_overlaps = sum(len(v) for v in overlap_groups.values())
        # Only report if there's a meaningful number
        evidence = []
        for key, handles in list(overlap_groups.items())[:5]:
            parts = key.split(",")
            for handle in handles[:3]:
                found = index.get_by_handle(handle)
                if found is not None:
                    evidence.append(
                        EvidenceRef(
                            entity_handle=handle,
                            layer=found.layer,
                            entity_type=found.entity_type.value,
                            location=(found.insert_point.x, found.insert_point.y)
                            if found.insert_point
                            else None,
                            description=(
                                f"Overlaps with {len(handles) - 1} other "
                                f"entity(ies) at ({parts[0]}, {parts[1]})"
                            ),
                        )
                    )

        issues.append(
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.OVERLAP,
                title=f"{len(overlap_groups)} location(s) with overlapping entities",
                description=(
                    f"{total_overlaps} entities share coordinates with others "
                    f"on the same layer across {len(overlap_groups)} location(s). "
                    "These may be unintentional duplicates."
                ),
                evidence=evidence,
                check_name="check_overlapping_entities",
            )
        )

    return issues


def _check_missing_text_content(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag TEXT/MTEXT entities with empty or whitespace-only content."""
    issues = []
    empty_texts = []

    for entity in context.entities:
        if entity.entity_type not in (EntityType.TEXT, EntityType.MTEXT):
            continue
        if not entity.text_content or not entity.text_content.strip():
            empty_texts.append(entity)

    if empty_texts:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title=(
                    f"{len(empty_texts)} empty text entit{'y' if len(empty_texts) == 1 else 'ies'}"
                ),
                description=(
                    f"{len(empty_texts)} TEXT/MTEXT "
                    f"entit{'y has' if len(empty_texts) == 1 else 'ies have'} "
                    "empty or whitespace-only content. These may be placeholder "
                    "text that was never filled in."
                ),
                evidence=[
                    EvidenceRef(
                        entity_handle=e.handle,
                        layer=e.layer,
                        entity_type=e.entity_type.value,
                        location=(e.insert_point.x, e.insert_point.y) if e.insert_point else None,
                        description="Empty text content",
                    )
                    for e in empty_texts[:10]
                ],
                check_name="check_missing_text_content",
            )
        )

    return issues


def _check_dimension_coverage(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Check if the drawing has dimensions relative to its structural content.

    A structural drawing with many lines but zero dimensions likely has
    missing dimension annotations.
    """
    issues = []
    dims = index.get_by_type(EntityType.DIMENSION)
    lines = index.get_by_type(EntityType.LINE)
    polylines = index.get_by_type(EntityType.LWPOLYLINE)
    geometry_count = len(lines) + len(polylines)

    if geometry_count >= 10 and len(dims) == 0:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.DIMENSION,
                title="No dimensions found",
                description=(
                    f"Drawing has {geometry_count} geometric entities (lines + polylines) "
                    "but no DIMENSION entities. Critical dimensions may be missing."
                ),
                evidence=[],
                check_name="check_dimension_coverage",
            )
        )
    elif geometry_count >= 20 and len(dims) < geometry_count * 0.05:
        # Less than 5% dimension-to-geometry ratio
        issues.append(
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.DIMENSION,
                title="Low dimension coverage",
                description=(
                    f"Only {len(dims)} dimension(s) for {geometry_count} geometric entities "
                    f"({len(dims) / geometry_count * 100:.0f}% ratio). "
                    "Consider adding dimensions to key measurements."
                ),
                evidence=[],
                check_name="check_dimension_coverage",
            )
        )

    return issues


def _check_entity_type_distribution(
    context: DrawingContext,
    index: EntityIndex,
) -> list[HealthIssue]:
    """Flag drawings with suspicious entity type distributions.

    A drawing with only INSERT entities (no lines) or only text (no geometry)
    may indicate a corrupt or incomplete import.
    """
    issues = []
    counts = Counter(e.entity_type for e in context.entities)

    if context.entity_count == 0:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title="Empty drawing",
                description="Drawing contains no supported entities.",
                evidence=[],
                check_name="check_entity_type_distribution",
            )
        )
        return issues

    # All text, no geometry
    text_count = counts.get(EntityType.TEXT, 0) + counts.get(EntityType.MTEXT, 0)
    geom_count = (
        counts.get(EntityType.LINE, 0)
        + counts.get(EntityType.LWPOLYLINE, 0)
        + counts.get(EntityType.CIRCLE, 0)
        + counts.get(EntityType.ARC, 0)
    )

    if text_count > 0 and geom_count == 0 and context.entity_count > 5:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.GENERAL,
                title="Text-only drawing",
                description=(
                    f"Drawing has {text_count} text entities but no geometric entities "
                    "(lines, polylines, circles, arcs). This may be a title sheet "
                    "or a partially loaded drawing."
                ),
                evidence=[],
                check_name="check_entity_type_distribution",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Zone-dependent checks
# ---------------------------------------------------------------------------


def _check_unnamed_zones(context: DrawingContext) -> list[HealthIssue]:
    """Flag detected zones that have no associated text label.

    Requires zone_detector — imported lazily to avoid circular dependency.
    """
    issues: list[HealthIssue] = []
    try:
        from .zone_detector import detect_zones
    except ImportError:
        return issues

    result = detect_zones(context)

    unnamed = [z for z in result.zones if z.inferred_type is None]
    if unnamed:
        issues.append(
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.ZONE,
                title=f"{len(unnamed)} zone(s) without labels",
                description=(
                    f"{len(unnamed)} of {result.zone_count} detected zones have "
                    "no associated text label. Consider adding room names or zone "
                    "identifiers for clarity."
                ),
                evidence=[
                    EvidenceRef(
                        location=(z.centroid.x, z.centroid.y),
                        description=(
                            f"Unnamed zone (area: {z.area:.0f} sq units) "
                            f"at ({z.centroid.x:.0f}, {z.centroid.y:.0f})"
                        ),
                    )
                    for z in unnamed[:5]
                ],
                check_name="check_unnamed_zones",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def _compute_score(issues: list[HealthIssue], entity_count: int) -> float:
    """Compute a 0-100 health score from issues.

    Deductions:
    - CRITICAL: -20 each (capped at -60)
    - WARNING: -5 each (capped at -30)
    - INFO: -1 each (capped at -10)

    Score cannot go below 0.
    """
    if entity_count == 0:
        return 0.0

    critical = sum(1 for i in issues if i.severity == HealthSeverity.CRITICAL)
    warning = sum(1 for i in issues if i.severity == HealthSeverity.WARNING)
    info = sum(1 for i in issues if i.severity == HealthSeverity.INFO)

    deductions = min(critical * 20, 60) + min(warning * 5, 30) + min(info * 1, 10)

    return max(0.0, 100.0 - deductions)


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    _check_polylines_missing_geometry,
    _check_inconsistent_text_heights,
    _check_orphan_layers,
    _check_overlapping_entities,
    _check_missing_text_content,
    _check_dimension_coverage,
    _check_entity_type_distribution,
]
