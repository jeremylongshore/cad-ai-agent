"""Design operations — deterministic analysis pipelines for design workflows.

LayoutRecommender:   Analyze entity layout, density, placement patterns.
RevisionSummarizer:  Translate comparison/changeset into plain-language summaries.
TakeoffGenerator:    Count block inserts, layer entities, and text-derived quantities.
ScopeBuilder:        Assemble all of the above into a scope-style report.

All outputs are evidence-grounded. No LLM calls. No edit operations produced.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from ..models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
)
from ..models.design_ops_schema import (
    ChangeSummaryEntry,
    CustomerRevisionSummary,
    LayoutRecommendation,
    LayoutRecommendationResult,
    RecommendationType,
    ScopeSection,
    ScopeSectionType,
    ScopeSummary,
    TakeoffCandidateResult,
    TakeoffConfidence,
    TakeoffItem,
)
from ..models.response_schema import EvidenceRef
from .text_utils import describe_entity, entity_to_evidence

if TYPE_CHECKING:
    from ..models.comparison_schema import ComparisonResult
    from ..models.ops_schema import ChangeSet
    from ..models.qna_schema import RegionContext


_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})


# ---------------------------------------------------------------------------
# 09.1 — Layout Recommender
# ---------------------------------------------------------------------------


class LayoutRecommender:
    """Analyze drawing layout and produce bounded recommendations."""

    def recommend(
        self,
        context: DrawingContext,
        prompt: str,
        region: RegionContext | None = None,
    ) -> LayoutRecommendationResult:
        entities = list(region.entities) if region else list(context.entities)
        if not entities:
            return LayoutRecommendationResult(
                drawing_summary="Empty drawing — no entities to analyze.",
                ambiguity_flags=["empty_drawing"],
                limitations=["No entities available for analysis."],
            )

        recommendations: list[LayoutRecommendation] = []
        ambiguity_flags: list[str] = []
        limitations: list[str] = []

        # Layer distribution analysis
        layer_counts = Counter(e.layer for e in entities)
        layer_recs = self._analyze_layer_distribution(entities, layer_counts)
        recommendations.extend(layer_recs)

        # Entity density analysis
        density_recs = self._analyze_density(entities)
        recommendations.extend(density_recs)

        # Block placement patterns
        block_recs = self._analyze_block_placement(entities)
        recommendations.extend(block_recs)

        # Text label analysis
        text_recs = self._analyze_text_labels(entities)
        recommendations.extend(text_recs)

        # Region-specific caveats
        if region and not region.is_whole_drawing:
            ambiguity_flags.append("partial_region")
            limitations.append("Analysis is limited to the selected region, not the whole drawing.")
            for rec in recommendations:
                rec.confidence = max(0.0, rec.confidence - 0.1)

        if region and "context_truncated" in region.ambiguity_flags:
            ambiguity_flags.append("context_truncated")
            limitations.append("Entity count was capped; some entities may be excluded.")

        # Sparse evidence check
        text_count = sum(1 for e in entities if e.entity_type in _TEXT_TYPES)
        if text_count < 3:
            ambiguity_flags.append("sparse_text_evidence")
            limitations.append("Few text labels available — recommendations may lack context.")
            for rec in recommendations:
                rec.confidence = max(0.0, rec.confidence - 0.15)

        # Aggregate confidence = min of all recommendations
        agg_conf = min((r.confidence for r in recommendations), default=0.0)

        total = len(recommendations)
        return LayoutRecommendationResult(
            recommendations=recommendations,
            drawing_summary=self._build_summary(entities, layer_counts),
            total_recommendations=total,
            aggregate_confidence=round(agg_conf, 2),
            ambiguity_flags=ambiguity_flags,
            limitations=limitations,
        )

    # -- Internal analyzers --

    def _analyze_layer_distribution(
        self,
        entities: list[EntityRef],
        layer_counts: Counter[str],
    ) -> list[LayoutRecommendation]:
        recs: list[LayoutRecommendation] = []
        total = len(entities)
        if total == 0:
            return recs

        for layer, count in layer_counts.most_common():
            ratio = count / total
            if ratio > 0.6 and total > 10:
                evidence = [entity_to_evidence(e) for e in entities if e.layer == layer][:5]
                recs.append(
                    LayoutRecommendation(
                        type=RecommendationType.GENERAL_OBSERVATION,
                        title=f"High entity concentration on layer '{layer}'",
                        description=(
                            f"Layer '{layer}' contains {count} of {total} entities "
                            f"({ratio:.0%}). Consider splitting into sub-layers."
                        ),
                        rationale="Concentrated layers can be harder to manage and filter.",
                        evidence=evidence,
                        confidence=0.85,
                        affected_layers=[layer],
                    )
                )
                break  # Only report the most concentrated layer

        return recs

    def _analyze_density(
        self,
        entities: list[EntityRef],
    ) -> list[LayoutRecommendation]:
        recs: list[LayoutRecommendation] = []
        positioned = [e for e in entities if e.insert_point is not None]
        if len(positioned) < 5:
            return recs

        xs = [e.insert_point.x for e in positioned]  # type: ignore[union-attr]
        ys = [e.insert_point.y for e in positioned]  # type: ignore[union-attr]
        x_range = max(xs) - min(xs) if xs else 0
        y_range = max(ys) - min(ys) if ys else 0
        area = max(x_range * y_range, 1.0)
        density = len(positioned) / area

        if density > 0.1:
            sample = positioned[:5]
            evidence = [entity_to_evidence(e) for e in sample]
            recs.append(
                LayoutRecommendation(
                    type=RecommendationType.PLACEMENT_GUIDANCE,
                    title="High entity density detected",
                    description=(
                        f"{len(positioned)} positioned entities across "
                        f"{x_range:.0f}x{y_range:.0f} area "
                        f"(density: {density:.3f}/unit\u00b2)."
                    ),
                    rationale="Dense areas may benefit from spacing adjustments.",
                    evidence=evidence,
                    confidence=0.70,
                )
            )

        return recs

    def _analyze_block_placement(
        self,
        entities: list[EntityRef],
    ) -> list[LayoutRecommendation]:
        recs: list[LayoutRecommendation] = []
        inserts = [e for e in entities if e.entity_type == EntityType.INSERT]
        if not inserts:
            return recs

        block_counts = Counter(e.block_name for e in inserts if e.block_name)
        for block_name, count in block_counts.most_common(3):
            if count >= 3:
                block_entities = [e for e in inserts if e.block_name == block_name]
                evidence = [entity_to_evidence(e) for e in block_entities[:5]]
                layers = sorted({e.layer for e in block_entities})
                recs.append(
                    LayoutRecommendation(
                        type=RecommendationType.REGION_USAGE,
                        title=f"Repeated block '{block_name}' ({count} instances)",
                        description=(
                            f"Block '{block_name}' appears {count} times. "
                            f"Placement pattern analysis available."
                        ),
                        rationale="Repeated blocks often indicate structural grid or fixture.",
                        evidence=evidence,
                        confidence=0.90,
                        affected_layers=layers,
                    )
                )

        return recs

    def _analyze_text_labels(
        self,
        entities: list[EntityRef],
    ) -> list[LayoutRecommendation]:
        recs: list[LayoutRecommendation] = []
        text_entities = [e for e in entities if e.entity_type in _TEXT_TYPES]
        if not text_entities:
            return recs

        # Check for low-trust text
        low_trust = [
            e for e in text_entities if e.text_geometry and not e.text_geometry.is_high_trust
        ]
        if low_trust:
            evidence = [entity_to_evidence(e) for e in low_trust[:3]]
            recs.append(
                LayoutRecommendation(
                    type=RecommendationType.GENERAL_OBSERVATION,
                    title=f"Low-trust text detected ({len(low_trust)} entities)",
                    description=(
                        f"{len(low_trust)} text entities have OCR or vector-outline "
                        f"provenance. Labels may be inaccurate."
                    ),
                    rationale="OCR-derived text has lower confidence for identification.",
                    evidence=evidence,
                    confidence=0.60,
                    caveats=["Text content may not exactly match the original drawing."],
                )
            )

        return recs

    def _build_summary(
        self,
        entities: list[EntityRef],
        layer_counts: Counter[str],
    ) -> str:
        type_counts = Counter(e.entity_type.value for e in entities)
        parts = [f"{len(entities)} entities across {len(layer_counts)} layers"]
        for etype, count in type_counts.most_common(3):
            parts.append(f"{count} {etype}")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# 09.2 — Revision Summarizer
# ---------------------------------------------------------------------------


class RevisionSummarizer:
    """Translate comparison results or changesets into plain-language summaries."""

    def summarize(
        self,
        comparison_result: ComparisonResult | None = None,
        changeset: ChangeSet | None = None,
        context: DrawingContext | None = None,
    ) -> CustomerRevisionSummary:
        if comparison_result is not None:
            return self._from_comparison(comparison_result, context)
        if changeset is not None:
            return self._from_changeset(changeset, context)
        return CustomerRevisionSummary(
            headline="No revision data available.",
            caveats=["Neither comparison result nor changeset was provided."],
            missing_context=["comparison_result", "changeset"],
        )

    def _from_comparison(
        self,
        result: ComparisonResult,
        context: DrawingContext | None,
    ) -> CustomerRevisionSummary:
        from ..models.comparison_schema import ChangeCategory

        entries: list[ChangeSummaryEntry] = []
        areas: set[str] = set()
        ambiguity_flags: list[str] = []
        caveats: list[str] = []

        category_counts: Counter[str] = Counter()
        for change in result.changes:
            if change.category == ChangeCategory.UNCHANGED:
                continue
            category_counts[change.category.value] += 1

            # Build plain-language description
            snapshot = change.revision_snapshot or change.master_snapshot
            if snapshot is None:
                continue

            layer = snapshot.layer
            areas.add(layer)
            entity_type = snapshot.entity_type.value if snapshot.entity_type else "entity"

            desc = self._plain_description(change.category, entity_type, snapshot)
            tech = self._technical_detail(change)

            evidence: list[EvidenceRef] = []
            if snapshot.handle:
                evidence.append(
                    EvidenceRef(
                        entity_handle=snapshot.handle,
                        layer=layer,
                        entity_type=entity_type,
                        description=desc,
                    )
                )

            entries.append(
                ChangeSummaryEntry(
                    change_type=change.category.value,
                    plain_description=desc,
                    technical_detail=tech,
                    layer=layer,
                    evidence=evidence,
                    confidence=change.confidence,
                )
            )

        # Build headline
        total = sum(category_counts.values())
        parts = []
        for cat in ["added", "removed", "modified", "moved"]:
            cnt = category_counts.get(cat, 0)
            if cnt > 0:
                parts.append(f"{cnt} {cat}")
        headline = (
            f"{total} change(s) detected: {', '.join(parts)}" if parts else "No changes detected."
        )

        if result.warnings:
            caveats.extend(result.warnings)

        return CustomerRevisionSummary(
            headline=headline,
            key_changes=entries,
            overall_assessment=self._overall_assessment(category_counts, total),
            change_count=total,
            areas_affected=sorted(areas),
            ambiguity_flags=ambiguity_flags,
            caveats=caveats,
        )

    def _from_changeset(
        self,
        changeset: ChangeSet,
        context: DrawingContext | None,
    ) -> CustomerRevisionSummary:
        entries: list[ChangeSummaryEntry] = []
        areas: set[str] = set()

        for op in changeset.operations:
            op_type = op.op_type.value if hasattr(op.op_type, "value") else str(op.op_type)
            layer = op.target_layer or "unknown"
            areas.add(layer)

            desc = self._op_to_plain(op_type, op, context)
            entries.append(
                ChangeSummaryEntry(
                    change_type=op_type,
                    plain_description=desc,
                    layer=layer,
                )
            )

        total = len(entries)
        headline = f"{total} planned operation(s)." if total > 0 else "No operations planned."

        return CustomerRevisionSummary(
            headline=headline,
            key_changes=entries,
            overall_assessment=f"{total} edit operation(s) from the change plan.",
            change_count=total,
            areas_affected=sorted(areas),
        )

    # -- Helpers --

    def _plain_description(self, category: object, entity_type: str, snapshot: object) -> str:
        cat = str(category.value) if hasattr(category, "value") else str(category)
        text_hint = ""
        if hasattr(snapshot, "text_content") and snapshot.text_content:
            preview = snapshot.text_content[:40]
            text_hint = f" ('{preview}')"

        templates = {
            "added": f"A {entity_type} was added{text_hint}",
            "removed": f"A {entity_type} was removed{text_hint}",
            "modified": f"A {entity_type} was modified{text_hint}",
            "moved": f"A {entity_type} was repositioned{text_hint}",
        }
        return templates.get(cat, f"A {entity_type} was changed{text_hint}")

    def _technical_detail(self, change: object) -> str:
        parts: list[str] = []
        if hasattr(change, "displacement") and change.displacement:
            d = change.displacement
            parts.append(f"displacement=({d.x:.1f}, {d.y:.1f})")
        if hasattr(change, "modifications") and change.modifications:
            parts.append(f"fields={list(change.modifications.keys())}")
        return "; ".join(parts) if parts else ""

    def _op_to_plain(self, op_type: str, op: object, context: DrawingContext | None) -> str:
        entity_desc = ""
        if context and hasattr(op, "target_handle") and op.target_handle:
            entity = context.get_entity_by_handle(op.target_handle)
            if entity:
                entity_desc = describe_entity(entity)

        templates = {
            "move_entity": "An element was repositioned",
            "delete_entity": "An element was removed",
            "edit_text": "A text label was updated",
            "add_block": "A new block was inserted",
        }
        base = templates.get(op_type, f"Operation: {op_type}")
        return f"{base} — {entity_desc}" if entity_desc else base

    def _overall_assessment(self, counts: Counter[str], total: int) -> str:
        if total == 0:
            return "No changes were detected between the drawings."
        parts = []
        if counts.get("added"):
            parts.append(f"{counts['added']} element(s) were added")
        if counts.get("removed"):
            parts.append(f"{counts['removed']} element(s) were removed")
        if counts.get("modified"):
            parts.append(f"{counts['modified']} element(s) were modified")
        if counts.get("moved"):
            parts.append(f"{counts['moved']} element(s) were repositioned")
        return ". ".join(parts) + "."


# ---------------------------------------------------------------------------
# 09.3 — Takeoff Generator
# ---------------------------------------------------------------------------

_QUANTITY_PATTERN = re.compile(r"(\d+)\s*(?:x|ea|pcs?|units?|nos?\.?)\b", re.IGNORECASE)


class TakeoffGenerator:
    """Generate takeoff candidates by counting blocks, layers, and text hints."""

    def generate(
        self,
        context: DrawingContext,
        prompt: str,
        region: RegionContext | None = None,
    ) -> TakeoffCandidateResult:
        entities = list(region.entities) if region else list(context.entities)
        if not entities:
            return TakeoffCandidateResult(
                caveats=["No entities in drawing."],
                ambiguity_flags=["empty_drawing"],
            )

        items: list[TakeoffItem] = []
        provenance_warnings: list[str] = []
        ambiguity_flags: list[str] = []
        caveats: list[str] = []

        # Block-based counting
        block_items = self._count_blocks(entities)
        items.extend(block_items)

        # Layer-based counting (only for layers not already covered by blocks)
        block_layers = {item.source_layer for item in block_items}
        layer_items = self._count_by_layer(entities, exclude_layers=block_layers)
        items.extend(layer_items)

        # Text-derived quantity hints
        text_items, text_warnings = self._extract_text_quantities(entities)
        items.extend(text_items)
        provenance_warnings.extend(text_warnings)

        # Region caveats
        if region and not region.is_whole_drawing:
            ambiguity_flags.append("partial_region")
            caveats.append("Counts are from the selected region only, not the entire drawing.")

        # Compute aggregates
        total_items = len(items)
        total_quantity = sum(item.quantity for item in items)

        # Aggregate confidence
        if items:
            confidence_order = [
                TakeoffConfidence.ESTIMATE_ONLY,
                TakeoffConfidence.LOW,
                TakeoffConfidence.MEDIUM,
                TakeoffConfidence.HIGH,
            ]
            worst = min(items, key=lambda i: confidence_order.index(i.confidence))
            agg = worst.confidence
        else:
            agg = TakeoffConfidence.MEDIUM

        return TakeoffCandidateResult(
            items=items,
            total_items=total_items,
            total_quantity_items=total_quantity,
            aggregate_confidence=agg,
            ambiguity_flags=ambiguity_flags,
            provenance_warnings=provenance_warnings,
            caveats=caveats,
        )

    def _count_blocks(self, entities: list[EntityRef]) -> list[TakeoffItem]:
        inserts = [e for e in entities if e.entity_type == EntityType.INSERT and e.block_name]
        if not inserts:
            return []

        by_block: dict[str, list[EntityRef]] = {}
        for e in inserts:
            by_block.setdefault(e.block_name, []).append(e)  # type: ignore[arg-type]

        items: list[TakeoffItem] = []
        for block_name, block_entities in sorted(by_block.items()):
            layers = sorted({e.layer for e in block_entities})
            handles = [e.handle for e in block_entities]
            items.append(
                TakeoffItem(
                    name=block_name,
                    quantity=len(block_entities),
                    unit="ea",
                    source_layer=layers[0],
                    source_block_name=block_name,
                    entity_handles=handles,
                    confidence=TakeoffConfidence.HIGH,
                )
            )
        return items

    def _count_by_layer(
        self,
        entities: list[EntityRef],
        exclude_layers: set[str],
    ) -> list[TakeoffItem]:
        items: list[TakeoffItem] = []
        layer_counts: Counter[str] = Counter()
        layer_handles: dict[str, list[str]] = {}

        for e in entities:
            if e.layer in exclude_layers:
                continue
            if e.entity_type == EntityType.INSERT:
                continue  # Already counted in block pass
            layer_counts[e.layer] += 1
            layer_handles.setdefault(e.layer, []).append(e.handle)

        for layer, count in layer_counts.most_common():
            if count >= 2:
                items.append(
                    TakeoffItem(
                        name=f"Entities on '{layer}'",
                        quantity=count,
                        source_layer=layer,
                        entity_handles=layer_handles.get(layer, [])[:20],
                        confidence=TakeoffConfidence.MEDIUM,
                        caveats=["Count based on layer membership, not element type."],
                    )
                )
        return items

    def _extract_text_quantities(
        self,
        entities: list[EntityRef],
    ) -> tuple[list[TakeoffItem], list[str]]:
        items: list[TakeoffItem] = []
        warnings: list[str] = []

        text_entities = [e for e in entities if e.entity_type in _TEXT_TYPES and e.text_content]
        for e in text_entities:
            match = _QUANTITY_PATTERN.search(e.text_content or "")
            if not match:
                continue

            qty = int(match.group(1))
            if qty <= 0 or qty > 10000:
                continue

            # SQ67: check text provenance
            is_ocr = e.text_geometry is not None and not e.text_geometry.is_high_trust
            if is_ocr:
                confidence = TakeoffConfidence.ESTIMATE_ONLY
                caveat_list = [
                    "Quantity extracted from OCR text — may be inaccurate.",
                    f"Text provenance: {e.text_geometry.provenance.value}",  # type: ignore[union-attr]
                ]
                warnings.append(
                    f"OCR-derived quantity '{e.text_content}' on layer '{e.layer}' "
                    f"— confidence downgraded to ESTIMATE_ONLY."
                )
                provenance = e.text_geometry.provenance if e.text_geometry else None  # type: ignore[union-attr]
            else:
                confidence = TakeoffConfidence.MEDIUM
                caveat_list = ["Quantity derived from text label — verify against schedule."]
                provenance = e.text_geometry.provenance if e.text_geometry else None

            label = e.text_content[:60] if e.text_content else "unknown"
            items.append(
                TakeoffItem(
                    name=f"Text-derived: '{label}'",
                    quantity=qty,
                    source_layer=e.layer,
                    entity_handles=[e.handle],
                    confidence=confidence,
                    caveats=caveat_list,
                    text_provenance=provenance,
                )
            )

        return items, warnings


# ---------------------------------------------------------------------------
# 09.4 — Scope Builder
# ---------------------------------------------------------------------------


class ScopeBuilder:
    """Assemble layout, summary, and takeoff into a scope-style report."""

    def build(
        self,
        context: DrawingContext,
        prompt: str,
        region: RegionContext | None = None,
        comparison_result: ComparisonResult | None = None,
        changeset: ChangeSet | None = None,
    ) -> ScopeSummary:
        sections: list[ScopeSection] = []
        omitted: list[str] = []
        all_caveats: list[str] = []
        ambiguity_flags: list[str] = []

        # Layout recommendations
        layout_result = LayoutRecommender().recommend(context, prompt, region)
        if layout_result.recommendations:
            sections.append(
                ScopeSection(
                    section_type=ScopeSectionType.LAYOUT_RECOMMENDATIONS,
                    title="Layout Recommendations",
                    content=layout_result.model_dump(),
                    confidence=layout_result.aggregate_confidence,
                    caveats=layout_result.limitations,
                )
            )
        else:
            omitted.append("layout_recommendations")

        ambiguity_flags.extend(layout_result.ambiguity_flags)

        # Revision summary
        if comparison_result is not None or changeset is not None:
            summary_result = RevisionSummarizer().summarize(
                comparison_result=comparison_result,
                changeset=changeset,
                context=context,
            )
            sections.append(
                ScopeSection(
                    section_type=ScopeSectionType.REVISION_SUMMARY,
                    title="Revision Summary",
                    content=summary_result.model_dump(),
                    confidence=min(
                        (e.confidence for e in summary_result.key_changes),
                        default=0.5,
                    ),
                    caveats=summary_result.caveats,
                )
            )
            all_caveats.extend(summary_result.caveats)
        else:
            omitted.append("revision_summary")

        # Takeoff candidates
        takeoff_result = TakeoffGenerator().generate(context, prompt, region)
        if takeoff_result.items:
            _conf_to_float = {
                TakeoffConfidence.HIGH: 0.95,
                TakeoffConfidence.MEDIUM: 0.7,
                TakeoffConfidence.LOW: 0.4,
                TakeoffConfidence.ESTIMATE_ONLY: 0.2,
            }
            sections.append(
                ScopeSection(
                    section_type=ScopeSectionType.TAKEOFF_CANDIDATES,
                    title="Takeoff Candidates",
                    content=takeoff_result.model_dump(),
                    confidence=_conf_to_float.get(takeoff_result.aggregate_confidence, 0.5),
                    caveats=takeoff_result.caveats,
                )
            )
            all_caveats.extend(takeoff_result.caveats)
            ambiguity_flags.extend(takeoff_result.ambiguity_flags)
        else:
            omitted.append("takeoff_candidates")

        # Aggregate confidence = min of available sections
        agg_conf = min(
            (s.confidence for s in sections if s.available),
            default=0.0,
        )

        return ScopeSummary(
            sections=sections,
            aggregate_confidence=round(agg_conf, 2),
            ambiguity_flags=ambiguity_flags,
            omitted_sections=omitted,
            caveats=all_caveats,
        )
