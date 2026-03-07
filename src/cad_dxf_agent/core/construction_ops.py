"""Construction operations -- deterministic analysis pipelines for construction workflows.

GridAnalyzer:          Detect structural grids and compute bays between grid lines.
MarkupRedlineGenerator: Find revision clouds and report affected entities within bounds.
BatchConditionPlanner:  Group repeated block/text patterns across the drawing.
FieldSummaryBuilder:    Assemble all construction + design-ops into a field report.

All outputs are evidence-grounded. No LLM calls. No edit operations produced.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from ..models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
)
from ..models.construction_ops_schema import (
    BatchConditionResult,
    Bay,
    ConditionGroup,
    FieldSection,
    FieldSectionType,
    FieldSummary,
    GridDirection,
    GridLine,
    GridSummaryResult,
    RedlineEntry,
    RedlineReportResult,
    RevisionCloudInfo,
)
from .text_utils import entity_to_evidence, levenshtein_similarity

if TYPE_CHECKING:
    from ..models.comparison_schema import ComparisonResult
    from ..models.ops_schema import ChangeSet
    from ..models.qna_schema import RegionContext


_GRID_LAYER_PATTERN = re.compile(r"(GRID|COLUMN|AXIS)", re.IGNORECASE)
_CLOUD_LAYER_PATTERN = re.compile(r"(CLOUD|MARKUP|REVISION|REDLINE)", re.IGNORECASE)
_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})
_LINE_TYPES = frozenset({EntityType.LINE, EntityType.LWPOLYLINE})


# ---------------------------------------------------------------------------
# 10.1 -- Grid Analyzer
# ---------------------------------------------------------------------------


class GridAnalyzer:
    """Detect structural grids and compute bays between grid lines."""

    def analyze(
        self,
        context: DrawingContext,
        prompt: str,
        region: RegionContext | None = None,
    ) -> GridSummaryResult:
        entities = list(region.entities) if region else list(context.entities)
        if not entities:
            return GridSummaryResult(
                drawing_summary="Empty drawing -- no entities to analyze.",
                ambiguity_flags=["empty_drawing"],
                caveats=["No entities available for grid analysis."],
            )

        # Find line entities on grid-like layers
        grid_entities = [
            e for e in entities
            if e.entity_type in _LINE_TYPES
            and _GRID_LAYER_PATTERN.search(e.layer)
        ]

        if not grid_entities:
            return GridSummaryResult(
                drawing_summary=f"{len(entities)} entities, no grid lines detected.",
                ambiguity_flags=["no_grid_entities"],
                caveats=["No entities found on GRID/COLUMN/AXIS layers."],
            )

        # Build text index for label lookups
        text_entities = [
            e for e in entities if e.entity_type in _TEXT_TYPES and e.text_content
        ]

        # Classify lines as horizontal or vertical
        grid_lines: list[GridLine] = []
        for e in grid_entities:
            direction, position = self._classify_line(e)
            if direction is None:
                continue

            label = self._find_label(e, text_entities)
            confidence = 0.85 if label else 0.6

            grid_lines.append(
                GridLine(
                    direction=direction,
                    label=label,
                    position=position,
                    layer=e.layer,
                    entity_handle=e.handle,
                    confidence=confidence,
                )
            )

        # Sort by direction then position
        h_lines = sorted(
            [gl for gl in grid_lines if gl.direction == GridDirection.HORIZONTAL],
            key=lambda g: g.position,
        )
        v_lines = sorted(
            [gl for gl in grid_lines if gl.direction == GridDirection.VERTICAL],
            key=lambda g: g.position,
        )

        # Compute bays
        bays: list[Bay] = []
        bays.extend(self._compute_bays(h_lines, GridDirection.HORIZONTAL))
        bays.extend(self._compute_bays(v_lines, GridDirection.VERTICAL))

        # Aggregate confidence
        agg_conf = min(gl.confidence for gl in grid_lines) if grid_lines else 0.0

        caveats: list[str] = []
        ambiguity_flags: list[str] = []
        unlabeled = [gl for gl in grid_lines if not gl.label]
        if unlabeled:
            caveats.append(
                f"{len(unlabeled)} grid line(s) have no label -- "
                "labels inferred from position only."
            )
            ambiguity_flags.append("unlabeled_grid_lines")

        pattern_desc = (
            f"{len(v_lines)} vertical, {len(h_lines)} horizontal grid line(s)"
        )
        summary = (
            f"{len(grid_lines)} grid line(s) on {len({gl.layer for gl in grid_lines})} "
            f"layer(s); {len(bays)} bay(s) computed."
        )

        return GridSummaryResult(
            grid_lines=grid_lines,
            bays=bays,
            drawing_summary=summary,
            grid_pattern_description=pattern_desc,
            aggregate_confidence=round(agg_conf, 2),
            ambiguity_flags=ambiguity_flags,
            caveats=caveats,
        )

    def _classify_line(
        self, entity: EntityRef
    ) -> tuple[GridDirection | None, float]:
        """Classify a line as horizontal or vertical by start/end points."""
        if entity.entity_type == EntityType.LWPOLYLINE:
            vertices = entity.attributes.get("vertices", [])
            if len(vertices) < 2:
                return None, 0.0
            start, end = vertices[0], vertices[-1]
        elif entity.entity_type == EntityType.LINE:
            if entity.insert_point is None:
                return None, 0.0
            # For LINE entities we only have insert_point (start)
            # Without end point, use attributes if stored, otherwise skip
            end_point = entity.attributes.get("end_point")
            if end_point is None:
                return None, 0.0
            start = (entity.insert_point.x, entity.insert_point.y)
            end = end_point
        else:
            return None, 0.0

        dx = abs(start[0] - end[0])
        dy = abs(start[1] - end[1])

        # Tolerance for "straight" classification
        if dx < 0.01 and dy > 0.01:
            # Vertical line -- position is X coordinate
            return GridDirection.VERTICAL, start[0]
        elif dy < 0.01 and dx > 0.01:
            # Horizontal line -- position is Y coordinate
            return GridDirection.HORIZONTAL, start[1]
        return None, 0.0

    def _find_label(
        self, grid_entity: EntityRef, text_entities: list[EntityRef]
    ) -> str:
        """Find the nearest text label to a grid line endpoint."""
        if not grid_entity.insert_point or not text_entities:
            return ""

        gx, gy = grid_entity.insert_point.x, grid_entity.insert_point.y
        best_text = ""
        best_dist = 50.0  # max proximity threshold

        for te in text_entities:
            if not te.insert_point or not te.text_content:
                continue
            dist = math.hypot(te.insert_point.x - gx, te.insert_point.y - gy)
            if dist < best_dist:
                best_dist = dist
                best_text = te.text_content.strip()[:20]

        return best_text

    def _compute_bays(
        self, sorted_lines: list[GridLine], direction: GridDirection
    ) -> list[Bay]:
        """Compute bays as gaps between adjacent parallel grid lines."""
        bays: list[Bay] = []
        for i in range(len(sorted_lines) - 1):
            a = sorted_lines[i]
            b = sorted_lines[i + 1]
            dim = abs(b.position - a.position)
            label_a = a.label or f"L{i + 1}"
            label_b = b.label or f"L{i + 2}"
            bays.append(
                Bay(
                    label=f"{label_a}-{label_b}",
                    direction=direction,
                    start_line=label_a,
                    end_line=label_b,
                    dimension=round(dim, 2),
                )
            )
        return bays


# ---------------------------------------------------------------------------
# 10.2 -- Markup Redline Generator
# ---------------------------------------------------------------------------


class MarkupRedlineGenerator:
    """Find revision clouds and report affected entities within bounds."""

    def generate(
        self,
        context: DrawingContext,
        prompt: str,
    ) -> RedlineReportResult:
        entities = list(context.entities)
        if not entities:
            return RedlineReportResult(
                caveats=["No entities in drawing."],
                ambiguity_flags=["empty_drawing"],
            )

        # Find LWPOLYLINE entities on cloud/markup/revision layers
        clouds: list[tuple[EntityRef, list[tuple[float, float]]]] = []
        for e in entities:
            if e.entity_type != EntityType.LWPOLYLINE:
                continue
            if not _CLOUD_LAYER_PATTERN.search(e.layer):
                continue
            vertices = e.attributes.get("vertices", [])
            if not vertices:
                continue
            clouds.append((e, vertices))

        if not clouds:
            return RedlineReportResult(
                caveats=["No revision clouds found on CLOUD/MARKUP/REVISION/REDLINE layers."],
                ambiguity_flags=["no_clouds"],
            )

        entries: list[RedlineEntry] = []
        total_affected = 0

        for cloud_entity, vertices in clouds:
            # Compute bounding box
            xs = [v[0] for v in vertices]
            ys = [v[1] for v in vertices]
            min_pt = Point2D(x=min(xs), y=min(ys))
            max_pt = Point2D(x=max(xs), y=max(ys))

            cloud_info = RevisionCloudInfo(
                cloud_handle=cloud_entity.handle,
                layer=cloud_entity.layer,
                bounds=(min_pt, max_pt),
                vertex_count=len(vertices),
            )

            # Find entities within the bounding box (exclude the cloud itself)
            affected: list[EntityRef] = []
            affected_layers: set[str] = set()
            for e in entities:
                if e.handle == cloud_entity.handle:
                    continue
                if e.insert_point is None:
                    continue
                px, py = e.insert_point.x, e.insert_point.y
                if min_pt.x <= px <= max_pt.x and min_pt.y <= py <= max_pt.y:
                    affected.append(e)
                    affected_layers.add(e.layer)

            evidence = [entity_to_evidence(e) for e in affected[:10]]

            # Confidence based on vertex count and layer naming
            conf = 0.7
            if len(vertices) >= 8:
                conf = 0.85
            if "CLOUD" in cloud_entity.layer.upper():
                conf = min(conf + 0.1, 1.0)

            entry_count = len(affected)
            total_affected += entry_count

            desc_parts = [f"{entry_count} entity(ies) within cloud on '{cloud_entity.layer}'"]
            if affected_layers:
                desc_parts.append(f"across layer(s): {', '.join(sorted(affected_layers))}")

            entries.append(
                RedlineEntry(
                    cloud=cloud_info,
                    affected_entities=evidence,
                    affected_layers=sorted(affected_layers),
                    entity_count=entry_count,
                    description="; ".join(desc_parts),
                    confidence=conf,
                )
            )

        agg_conf = min(e.confidence for e in entries) if entries else 0.0

        return RedlineReportResult(
            entries=entries,
            total_clouds=len(entries),
            total_affected_entities=total_affected,
            aggregate_confidence=round(agg_conf, 2),
        )


# ---------------------------------------------------------------------------
# 10.3 -- Batch Condition Planner
# ---------------------------------------------------------------------------


class BatchConditionPlanner:
    """Group repeated block/text patterns across the drawing."""

    _MIN_INSTANCES = 3

    def plan(
        self,
        context: DrawingContext,
        prompt: str,
    ) -> BatchConditionResult:
        entities = list(context.entities)
        if not entities:
            return BatchConditionResult(
                caveats=["No entities in drawing."],
                ambiguity_flags=["empty_drawing"],
            )

        groups: list[ConditionGroup] = []
        ambiguity_flags: list[str] = []
        caveats: list[str] = []

        # Block-based grouping
        block_groups = self._group_by_block(entities)
        groups.extend(block_groups)

        # Text similarity grouping
        text_groups = self._group_by_text(entities)
        groups.extend(text_groups)

        # Sort by instance count descending
        groups.sort(key=lambda g: g.total_instances, reverse=True)

        total_groups = len(groups)
        total_instances = sum(g.total_instances for g in groups)

        if not groups:
            caveats.append("No repeated patterns found with 3+ instances.")

        agg_conf = min(g.confidence for g in groups) if groups else 0.0

        return BatchConditionResult(
            groups=groups,
            total_groups=total_groups,
            total_instances=total_instances,
            aggregate_confidence=round(agg_conf, 2),
            ambiguity_flags=ambiguity_flags,
            caveats=caveats,
        )

    def _group_by_block(self, entities: list[EntityRef]) -> list[ConditionGroup]:
        """Group INSERT entities by block_name with 3+ instances."""
        inserts = [e for e in entities if e.entity_type == EntityType.INSERT and e.block_name]
        by_block: dict[str, list[EntityRef]] = {}
        for e in inserts:
            by_block.setdefault(e.block_name, []).append(e)  # type: ignore[arg-type]

        groups: list[ConditionGroup] = []
        for block_name, block_entities in sorted(by_block.items()):
            if len(block_entities) < self._MIN_INSTANCES:
                continue

            instances = []
            for e in block_entities:
                inst: dict[str, object] = {"handle": e.handle, "layer": e.layer}
                if e.insert_point:
                    inst["x"] = e.insert_point.x
                    inst["y"] = e.insert_point.y
                instances.append(inst)

            # Confidence scales with instance count
            conf = min(0.95, 0.6 + len(block_entities) * 0.03)

            groups.append(
                ConditionGroup(
                    name=f"Block: {block_name}",
                    exemplar_handles=[block_entities[0].handle],
                    instances=instances,
                    total_instances=len(block_entities),
                    confidence=round(conf, 2),
                )
            )
        return groups

    def _group_by_text(self, entities: list[EntityRef]) -> list[ConditionGroup]:
        """Group TEXT/MTEXT entities with similar content (levenshtein >= 0.8)."""
        text_entities = [
            e for e in entities
            if e.entity_type in _TEXT_TYPES and e.text_content
        ]
        if not text_entities:
            return []

        # Cluster by similarity
        used: set[str] = set()
        groups: list[ConditionGroup] = []

        for e in text_entities:
            if e.handle in used:
                continue

            cluster = [e]
            used.add(e.handle)

            for other in text_entities:
                if other.handle in used:
                    continue
                sim = levenshtein_similarity(
                    (e.text_content or "").lower(),
                    (other.text_content or "").lower(),
                )
                if sim >= 0.8:
                    cluster.append(other)
                    used.add(other.handle)

            if len(cluster) < self._MIN_INSTANCES:
                continue

            instances = []
            for ce in cluster:
                inst: dict[str, object] = {
                    "handle": ce.handle,
                    "layer": ce.layer,
                    "text": ce.text_content,
                }
                if ce.insert_point:
                    inst["x"] = ce.insert_point.x
                    inst["y"] = ce.insert_point.y
                instances.append(inst)

            # Lower confidence for text-based groups
            conf = min(0.85, 0.5 + len(cluster) * 0.03)

            preview = (e.text_content or "")[:40]
            groups.append(
                ConditionGroup(
                    name=f"Text: '{preview}'",
                    exemplar_handles=[cluster[0].handle],
                    instances=instances,
                    total_instances=len(cluster),
                    confidence=round(conf, 2),
                    caveats=["Text similarity grouping -- verify content matches."],
                )
            )

        return groups


# ---------------------------------------------------------------------------
# 10.4 -- Field Summary Builder
# ---------------------------------------------------------------------------


class FieldSummaryBuilder:
    """Assemble all construction + design-ops into a field report."""

    def build(
        self,
        context: DrawingContext,
        prompt: str,
        region: RegionContext | None = None,
        comparison_result: ComparisonResult | None = None,
        changeset: ChangeSet | None = None,
    ) -> FieldSummary:
        sections: list[FieldSection] = []
        omitted: list[str] = []
        all_caveats: list[str] = []
        ambiguity_flags: list[str] = []

        # Grid summary
        grid_result = GridAnalyzer().analyze(context, prompt, region)
        if grid_result.grid_lines:
            sections.append(
                FieldSection(
                    section_type=FieldSectionType.GRID_SUMMARY,
                    title="Structural Grid Summary",
                    content=grid_result.model_dump(),
                    confidence=grid_result.aggregate_confidence,
                    caveats=grid_result.caveats,
                )
            )
            all_caveats.extend(grid_result.caveats)
            ambiguity_flags.extend(grid_result.ambiguity_flags)
        else:
            omitted.append("grid_summary")

        # Takeoff candidates (from EPIC-09)
        from .design_ops import TakeoffGenerator

        takeoff_result = TakeoffGenerator().generate(context, prompt, region)
        if takeoff_result.items:
            from ..models.design_ops_schema import TakeoffConfidence

            _conf_to_float = {
                TakeoffConfidence.HIGH: 0.95,
                TakeoffConfidence.MEDIUM: 0.7,
                TakeoffConfidence.LOW: 0.4,
                TakeoffConfidence.ESTIMATE_ONLY: 0.2,
            }
            sections.append(
                FieldSection(
                    section_type=FieldSectionType.TAKEOFF_SUMMARY,
                    title="Takeoff Candidates",
                    content=takeoff_result.model_dump(),
                    confidence=_conf_to_float.get(takeoff_result.aggregate_confidence, 0.5),
                    caveats=takeoff_result.caveats,
                )
            )
            all_caveats.extend(takeoff_result.caveats)
            ambiguity_flags.extend(takeoff_result.ambiguity_flags)
        else:
            omitted.append("takeoff_summary")

        # Revision changes (if comparison data available)
        if comparison_result is not None or changeset is not None:
            from .design_ops import RevisionSummarizer

            rev_result = RevisionSummarizer().summarize(
                comparison_result=comparison_result,
                changeset=changeset,
                context=context,
            )
            sections.append(
                FieldSection(
                    section_type=FieldSectionType.REVISION_CHANGES,
                    title="Revision Changes",
                    content=rev_result.model_dump(),
                    confidence=min(
                        (e.confidence for e in rev_result.key_changes),
                        default=0.5,
                    ),
                    caveats=rev_result.caveats,
                )
            )
            all_caveats.extend(rev_result.caveats)
        else:
            omitted.append("revision_changes")

        # Condition report
        batch_result = BatchConditionPlanner().plan(context, prompt)
        if batch_result.groups:
            sections.append(
                FieldSection(
                    section_type=FieldSectionType.CONDITION_REPORT,
                    title="Repeated Conditions",
                    content=batch_result.model_dump(),
                    confidence=batch_result.aggregate_confidence,
                    caveats=batch_result.caveats,
                )
            )
            all_caveats.extend(batch_result.caveats)
            ambiguity_flags.extend(batch_result.ambiguity_flags)
        else:
            omitted.append("condition_report")

        # Layout notes (from EPIC-09)
        from .design_ops import LayoutRecommender

        layout_result = LayoutRecommender().recommend(context, prompt, region)
        if layout_result.recommendations:
            sections.append(
                FieldSection(
                    section_type=FieldSectionType.LAYOUT_NOTES,
                    title="Layout Notes",
                    content=layout_result.model_dump(),
                    confidence=layout_result.aggregate_confidence,
                    caveats=layout_result.limitations,
                )
            )
            all_caveats.extend(layout_result.limitations)
            ambiguity_flags.extend(layout_result.ambiguity_flags)
        else:
            omitted.append("layout_notes")

        # Aggregate confidence = min of available sections
        agg_conf = min(
            (s.confidence for s in sections if s.available),
            default=0.0,
        )

        return FieldSummary(
            sections=sections,
            aggregate_confidence=round(agg_conf, 2),
            ambiguity_flags=ambiguity_flags,
            omitted_sections=omitted,
            caveats=all_caveats,
        )
