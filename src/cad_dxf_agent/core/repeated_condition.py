"""Repeated-condition detection — find similar entity clusters in a drawing.

Given an exemplar (set of entity handles), searches for spatially distinct
clusters with similar block names, text content, geometry, and layer context.
Scoring is deterministic (no LLM).
"""

from __future__ import annotations

import logging
import math
from collections import Counter

from ..models.cad_schema import (
    TEXT_PROVENANCE_DEFAULTS,
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
)
from ..models.repeated_condition_schema import (
    ConditionMatch,
    RepeatedConditionResult,
    SimilarityConfig,
    SimilaritySignal,
    SimilaritySignalType,
)
from ..models.response_schema import EvidenceRef
from .entity_index import EntityIndex
from .text_utils import levenshtein_similarity as _levenshtein_similarity

logger = logging.getLogger(__name__)

_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})


class _ExemplarProfile:
    """Pre-computed profile of the exemplar for comparison."""

    __slots__ = (
        "handles",
        "entities",
        "centroid",
        "radius",
        "block_names",
        "text_contents",
        "layer_distribution",
        "entity_types",
        "has_text",
        "has_blocks",
    )

    def __init__(self, entities: list[EntityRef]) -> None:
        self.handles = frozenset(e.handle for e in entities)
        self.entities = entities

        # Centroid
        pts = [e.insert_point for e in entities if e.insert_point is not None]
        if pts:
            cx = sum(p.x for p in pts) / len(pts)
            cy = sum(p.y for p in pts) / len(pts)
            self.centroid = Point2D(x=cx, y=cy)
            self.radius = max(math.hypot(p.x - cx, p.y - cy) for p in pts) if len(pts) > 1 else 0.0
        else:
            self.centroid = Point2D(x=0.0, y=0.0)
            self.radius = 50.0

        # Block names
        self.block_names = Counter(
            e.block_name for e in entities if e.entity_type == EntityType.INSERT and e.block_name
        )

        # Text content (normalized)
        self.text_contents: list[str] = [
            e.text_content.strip().lower()
            for e in entities
            if e.text_content and e.entity_type in _TEXT_TYPES
        ]

        # Layer distribution
        self.layer_distribution = Counter(e.layer.upper() for e in entities)

        # Type distribution
        self.entity_types = Counter(e.entity_type for e in entities)

        self.has_text = bool(self.text_contents)
        self.has_blocks = bool(self.block_names)


class ConditionDetector:
    """Find repeated conditions in a drawing given an exemplar."""

    def __init__(
        self,
        context: DrawingContext,
        config: SimilarityConfig | None = None,
    ) -> None:
        self._context = context
        self._index = EntityIndex(context)
        self._config = config or SimilarityConfig()

    def find_repeated(
        self,
        exemplar_handles: list[str],
        search_radius: float | None = None,
    ) -> RepeatedConditionResult:
        """Find repeated instances of the condition defined by exemplar_handles.

        Args:
            exemplar_handles: Entity handles defining one instance of the condition.
            search_radius: Override search radius. Defaults to exemplar radius * multiplier.

        Returns:
            RepeatedConditionResult with ranked candidates.
        """
        config = self._config

        # Build exemplar profile
        exemplar_entities = [
            e for h in exemplar_handles if (e := self._index.get_by_handle(h)) is not None
        ]
        if not exemplar_entities:
            return RepeatedConditionResult(
                exemplar_handles=exemplar_handles,
                exemplar_centroid=Point2D(x=0.0, y=0.0),
                summary="No valid entities found for the given handles.",
                config=config,
            )

        profile = _ExemplarProfile(exemplar_entities)
        effective_radius = search_radius or (profile.radius * config.search_radius_multiplier)

        # Find candidate seeds
        seeds = self._find_seeds(profile)
        if not seeds:
            return RepeatedConditionResult(
                exemplar_handles=exemplar_handles,
                exemplar_centroid=profile.centroid,
                search_radius=effective_radius,
                summary="No candidate matches found.",
                config=config,
            )

        # Cluster seeds into candidate groups
        clusters = self._cluster_seeds(seeds, profile, effective_radius)

        # Score each cluster
        candidates: list[ConditionMatch] = []
        for cluster_entities in clusters:
            match = self._score_cluster(cluster_entities, profile)
            if match.confidence >= config.min_confidence:
                # Apply caps
                match = self._apply_caps(match, profile)
                if match.confidence >= config.min_confidence:
                    candidates.append(match)

        # Sort by confidence descending
        candidates.sort(key=lambda m: m.confidence, reverse=True)

        # Cap results
        candidates = candidates[: config.max_results]

        # Flag ambiguity
        ambiguity_flags = self._detect_ambiguity(candidates)

        total = len(candidates)
        summary = self._build_summary(total, profile)

        return RepeatedConditionResult(
            exemplar_handles=exemplar_handles,
            exemplar_centroid=profile.centroid,
            candidates=candidates,
            total_found=total,
            search_radius=effective_radius,
            summary=summary,
            ambiguity_flags=ambiguity_flags,
            config=config,
        )

    def _find_seeds(self, profile: _ExemplarProfile) -> list[EntityRef]:
        """Find seed entities that share key features with the exemplar."""
        seed_handles: set[str] = set()
        seeds: list[EntityRef] = []

        # Seed from matching block names
        for block_name in profile.block_names:
            for entity in self._index.get_by_type(EntityType.INSERT):
                if (
                    entity.block_name == block_name
                    and entity.handle not in profile.handles
                    and entity.handle not in seed_handles
                ):
                    seed_handles.add(entity.handle)
                    seeds.append(entity)

        # Seed from matching text content
        for text in profile.text_contents:
            for entity in self._index.search_text(text):
                if entity.handle not in profile.handles and entity.handle not in seed_handles:
                    seed_handles.add(entity.handle)
                    seeds.append(entity)

        # Seed from same-layer entities of matching types
        for layer in profile.layer_distribution:
            for etype in profile.entity_types:
                for entity in self._index.filter(layer=layer, entity_type=etype.value):
                    if (
                        entity.handle not in profile.handles
                        and entity.handle not in seed_handles
                        and entity.insert_point is not None
                    ):
                        seed_handles.add(entity.handle)
                        seeds.append(entity)

        return seeds

    def _cluster_seeds(
        self,
        seeds: list[EntityRef],
        profile: _ExemplarProfile,
        search_radius: float,
    ) -> list[list[EntityRef]]:
        """Group seed entities into spatially distinct clusters."""
        cluster_radius = max(profile.radius, 10.0)
        min_separation = profile.radius * 0.5

        # Use block-based clustering when blocks exist
        if profile.has_blocks:
            return self._cluster_by_blocks(seeds, profile, cluster_radius, min_separation)

        # Fallback: cluster all seeds by spatial proximity
        return self._cluster_by_proximity(seeds, cluster_radius, min_separation, profile)

    def _cluster_by_blocks(
        self,
        seeds: list[EntityRef],
        profile: _ExemplarProfile,
        cluster_radius: float,
        min_separation: float,
    ) -> list[list[EntityRef]]:
        """Cluster around matching block instances."""
        clusters: list[list[EntityRef]] = []
        used: set[str] = set()

        # Primary block name from exemplar
        primary_blocks = set(profile.block_names.keys())

        # Find block anchors
        anchors = [
            s
            for s in seeds
            if s.entity_type == EntityType.INSERT
            and s.block_name in primary_blocks
            and s.insert_point is not None
        ]

        single_entity = len(profile.entities) == 1

        for anchor in anchors:
            if anchor.handle in used:
                continue

            assert anchor.insert_point is not None
            cx, cy = anchor.insert_point.x, anchor.insert_point.y

            # Skip if too close to exemplar
            dist_to_exemplar = math.hypot(cx - profile.centroid.x, cy - profile.centroid.y)
            if dist_to_exemplar < min_separation:
                continue

            # For single-entity exemplars, the anchor IS the cluster
            if single_entity:
                cluster = [anchor]
            else:
                # Gather nearby entities
                cluster = self._index.find_in_radius(cx, cy, cluster_radius)
                cluster = [
                    e for e in cluster if e.handle not in profile.handles and e.handle not in used
                ]

            if not cluster:
                continue

            for e in cluster:
                used.add(e.handle)
            clusters.append(cluster)

        return clusters

    def _cluster_by_proximity(
        self,
        seeds: list[EntityRef],
        cluster_radius: float,
        min_separation: float,
        profile: _ExemplarProfile,
    ) -> list[list[EntityRef]]:
        """Cluster seeds by spatial proximity without block anchors."""
        clusters: list[list[EntityRef]] = []
        used: set[str] = set()
        single_entity = len(profile.entities) == 1

        # Sort by position for deterministic clustering
        positioned = [s for s in seeds if s.insert_point is not None]
        positioned.sort(key=lambda e: (e.insert_point.x, e.insert_point.y))  # type: ignore[union-attr]

        for seed in positioned:
            if seed.handle in used:
                continue

            assert seed.insert_point is not None
            cx, cy = seed.insert_point.x, seed.insert_point.y

            dist_to_exemplar = math.hypot(cx - profile.centroid.x, cy - profile.centroid.y)
            if dist_to_exemplar < min_separation:
                continue

            # For single-entity exemplars, the seed IS the cluster
            if single_entity:
                cluster = [seed]
            else:
                cluster = self._index.find_in_radius(cx, cy, cluster_radius)
                cluster = [
                    e for e in cluster if e.handle not in profile.handles and e.handle not in used
                ]

            if not cluster:
                continue

            for e in cluster:
                used.add(e.handle)
            clusters.append(cluster)

        return clusters

    def _score_cluster(
        self,
        cluster: list[EntityRef],
        profile: _ExemplarProfile,
    ) -> ConditionMatch:
        """Score a candidate cluster against the exemplar profile."""
        signals: list[SimilaritySignal] = []

        # 1. Block name signal
        signals.append(self._score_block_name(cluster, profile))

        # 2. Text content signal
        signals.append(self._score_text_content(cluster, profile))

        # 3. Geometry shape signal
        signals.append(self._score_geometry(cluster, profile))

        # 4. Layer context signal
        signals.append(self._score_layer_context(cluster, profile))

        # 5. Spatial pattern signal
        signals.append(self._score_spatial_pattern(cluster, profile))

        # 6. Text geometry signal
        signals.append(self._score_text_geometry(cluster, profile))

        # Compute weighted confidence
        confidence = sum(s.weighted_score for s in signals)
        confidence = min(1.0, max(0.0, confidence))

        # Build evidence
        evidence = [_entity_to_evidence(e) for e in cluster[:10]]

        # Centroid
        pts = [e.insert_point for e in cluster if e.insert_point]
        if pts:
            cx = sum(p.x for p in pts) / len(pts)
            cy = sum(p.y for p in pts) / len(pts)
            centroid = Point2D(x=round(cx, 4), y=round(cy, 4))
        else:
            centroid = Point2D(x=0.0, y=0.0)

        # Explanation
        top_signals = sorted(signals, key=lambda s: s.weighted_score, reverse=True)[:3]
        explanation_parts = [f"{s.signal_type.value}: {s.detail}" for s in top_signals if s.detail]
        explanation = "; ".join(explanation_parts) if explanation_parts else "no strong signals"

        return ConditionMatch(
            entity_handles=[e.handle for e in cluster],
            confidence=round(confidence, 4),
            signals=signals,
            centroid=centroid,
            evidence=evidence,
            explanation=explanation,
        )

    def _score_block_name(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score block name overlap between cluster and exemplar."""
        if not profile.has_blocks:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.BLOCK_NAME,
                score=0.0,
                weight=self._config.block_name_weight,
                detail="exemplar has no blocks",
            )

        cluster_blocks = Counter(
            e.block_name for e in cluster if e.entity_type == EntityType.INSERT and e.block_name
        )

        if not cluster_blocks:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.BLOCK_NAME,
                score=0.0,
                weight=self._config.block_name_weight,
                detail="no blocks in candidate",
            )

        # Jaccard on block name multisets
        all_names = set(profile.block_names.keys()) | set(cluster_blocks.keys())
        if not all_names:
            score = 0.0
        else:
            matches = sum(
                min(profile.block_names.get(n, 0), cluster_blocks.get(n, 0)) for n in all_names
            )
            total = sum(
                max(profile.block_names.get(n, 0), cluster_blocks.get(n, 0)) for n in all_names
            )
            score = matches / total if total > 0 else 0.0

        matching_names = set(profile.block_names.keys()) & set(cluster_blocks.keys())
        detail = (
            f"matching blocks: {', '.join(sorted(matching_names))}"
            if matching_names
            else "no block overlap"
        )

        return SimilaritySignal(
            signal_type=SimilaritySignalType.BLOCK_NAME,
            score=round(score, 4),
            weight=self._config.block_name_weight,
            detail=detail,
        )

    def _score_text_content(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score text content similarity, weighted by provenance trust."""
        if not profile.has_text:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.TEXT_CONTENT,
                score=0.0,
                weight=self._config.text_content_weight,
                detail="exemplar has no text",
            )

        cluster_texts = [
            e.text_content.strip().lower()
            for e in cluster
            if e.text_content and e.entity_type in _TEXT_TYPES
        ]
        if not cluster_texts:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.TEXT_CONTENT,
                score=0.0,
                weight=self._config.text_content_weight,
                detail="no text in candidate",
            )

        # Best match for each exemplar text
        total_sim = 0.0
        match_count = 0
        for ex_text in profile.text_contents:
            best = max(
                (_levenshtein_similarity(ex_text, ct) for ct in cluster_texts),
                default=0.0,
            )
            total_sim += best
            if best > 0.5:
                match_count += 1

        score = total_sim / len(profile.text_contents) if profile.text_contents else 0.0

        # Trust level from provenance of cluster text entities
        trust = self._avg_text_trust(cluster)

        return SimilaritySignal(
            signal_type=SimilaritySignalType.TEXT_CONTENT,
            score=round(min(1.0, score), 4),
            weight=self._config.text_content_weight,
            detail=f"{match_count}/{len(profile.text_contents)} texts matched",
            trust_level=round(trust, 4),
        )

    def _score_geometry(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score entity type distribution similarity."""
        cluster_types = Counter(e.entity_type for e in cluster)

        if not profile.entity_types or not cluster_types:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.GEOMETRY_SHAPE,
                score=0.0,
                weight=self._config.geometry_shape_weight,
                detail="no entities to compare",
            )

        all_types = set(profile.entity_types.keys()) | set(cluster_types.keys())
        matches = sum(
            min(profile.entity_types.get(t, 0), cluster_types.get(t, 0)) for t in all_types
        )
        total = sum(max(profile.entity_types.get(t, 0), cluster_types.get(t, 0)) for t in all_types)
        score = matches / total if total > 0 else 0.0

        return SimilaritySignal(
            signal_type=SimilaritySignalType.GEOMETRY_SHAPE,
            score=round(score, 4),
            weight=self._config.geometry_shape_weight,
            detail=f"type overlap: {matches}/{total}",
        )

    def _score_layer_context(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score layer distribution similarity."""
        cluster_layers = Counter(e.layer.upper() for e in cluster)

        if not profile.layer_distribution or not cluster_layers:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.LAYER_CONTEXT,
                score=0.0,
                weight=self._config.layer_context_weight,
                detail="no layers to compare",
            )

        all_layers = set(profile.layer_distribution.keys()) | set(cluster_layers.keys())
        matches = sum(
            min(profile.layer_distribution.get(ly, 0), cluster_layers.get(ly, 0))
            for ly in all_layers
        )
        total = sum(
            max(profile.layer_distribution.get(ly, 0), cluster_layers.get(ly, 0))
            for ly in all_layers
        )
        score = matches / total if total > 0 else 0.0

        common = set(profile.layer_distribution.keys()) & set(cluster_layers.keys())
        detail = f"common layers: {', '.join(sorted(common))}" if common else "no layer overlap"

        return SimilaritySignal(
            signal_type=SimilaritySignalType.LAYER_CONTEXT,
            score=round(score, 4),
            weight=self._config.layer_context_weight,
            detail=detail,
        )

    def _score_spatial_pattern(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score entity count ratio as a proxy for spatial pattern similarity."""
        exemplar_count = len(profile.entities)
        cluster_count = len(cluster)

        if exemplar_count == 0 or cluster_count == 0:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.SPATIAL_PATTERN,
                score=0.0,
                weight=self._config.spatial_pattern_weight,
                detail="empty group",
            )

        ratio = min(exemplar_count, cluster_count) / max(exemplar_count, cluster_count)

        return SimilaritySignal(
            signal_type=SimilaritySignalType.SPATIAL_PATTERN,
            score=round(ratio, 4),
            weight=self._config.spatial_pattern_weight,
            detail=f"count ratio: {cluster_count}/{exemplar_count}",
        )

    def _score_text_geometry(
        self, cluster: list[EntityRef], profile: _ExemplarProfile
    ) -> SimilaritySignal:
        """Score text geometry similarity (height, rotation)."""
        exemplar_heights = [
            e.text_geometry.effective_height
            for e in profile.entities
            if e.text_geometry and e.text_geometry.effective_height
        ]
        cluster_heights = [
            e.text_geometry.effective_height
            for e in cluster
            if e.text_geometry and e.text_geometry.effective_height
        ]

        if not exemplar_heights or not cluster_heights:
            return SimilaritySignal(
                signal_type=SimilaritySignalType.TEXT_GEOMETRY,
                score=0.0,
                weight=self._config.text_geometry_weight,
                detail="no text geometry to compare",
            )

        # Compare average heights
        avg_ex = sum(exemplar_heights) / len(exemplar_heights)
        avg_cl = sum(cluster_heights) / len(cluster_heights)

        height_ratio = min(avg_ex, avg_cl) / max(avg_ex, avg_cl) if max(avg_ex, avg_cl) > 0 else 1.0

        return SimilaritySignal(
            signal_type=SimilaritySignalType.TEXT_GEOMETRY,
            score=round(height_ratio, 4),
            weight=self._config.text_geometry_weight,
            detail=f"height ratio: {height_ratio:.2f} (ex={avg_ex:.1f}, cl={avg_cl:.1f})",
        )

    def _apply_caps(self, match: ConditionMatch, profile: _ExemplarProfile) -> ConditionMatch:
        """Apply confidence caps for edge cases."""
        confidence = match.confidence

        # Single-entity block matches need higher confidence. If below threshold,
        # reject by zeroing confidence so it gets filtered in find_repeated.
        # Only applied to block-based matches where 0.70 is achievable;
        # text-only matches use the regular min_confidence threshold.
        if (
            len(match.entity_handles) == 1
            and profile.has_blocks
            and confidence < self._config.single_entity_min_confidence
        ):
            confidence = 0.0

        # Block-only matches (no text overlap) capped
        if profile.has_blocks and profile.has_text:
            text_signal = next(
                (s for s in match.signals if s.signal_type == SimilaritySignalType.TEXT_CONTENT),
                None,
            )
            if text_signal and text_signal.score < 0.1:
                confidence = min(confidence, self._config.block_only_cap)

        return match.model_copy(update={"confidence": round(confidence, 4)})

    def _detect_ambiguity(self, candidates: list[ConditionMatch]) -> list[str]:
        """Flag ambiguous near-ties in confidence."""
        flags: list[str] = []
        threshold = self._config.ambiguity_threshold

        for i in range(len(candidates) - 1):
            gap = candidates[i].confidence - candidates[i + 1].confidence
            if gap < threshold:
                flags.append(f"near-tie between candidates {i + 1} and {i + 2} (gap={gap:.4f})")

        return flags

    def _avg_text_trust(self, entities: list[EntityRef]) -> float:
        """Average text provenance trust level for entities with text geometry."""
        trusts: list[float] = []
        for e in entities:
            if e.text_geometry and e.entity_type in _TEXT_TYPES:
                prov = e.text_geometry.provenance
                defaults = TEXT_PROVENANCE_DEFAULTS.get(prov)
                if defaults:
                    trusts.append(defaults["content"])
                else:
                    trusts.append(1.0)

        return sum(trusts) / len(trusts) if trusts else 1.0

    def _build_summary(self, total: int, profile: _ExemplarProfile) -> str:
        """Build human-readable summary."""
        if total == 0:
            return "No repeated conditions found matching the exemplar."

        parts = [f"Found {total} repeated condition{'s' if total != 1 else ''}"]

        if profile.has_blocks:
            names = ", ".join(sorted(profile.block_names.keys())[:3])
            parts.append(f"matching block{'s' if len(profile.block_names) > 1 else ''}: {names}")

        if profile.has_text:
            sample = profile.text_contents[0][:30]
            parts.append(f'with text like "{sample}"')

        return " ".join(parts) + "."


# --- Helpers ---


def _entity_to_evidence(entity: EntityRef) -> EvidenceRef:
    """Convert an EntityRef to an EvidenceRef for result payloads."""
    location = None
    if entity.insert_point:
        location = (entity.insert_point.x, entity.insert_point.y)

    return EvidenceRef(
        entity_handle=entity.handle,
        layer=entity.layer,
        entity_type=entity.entity_type.value,
        location=location,
        text_excerpt=entity.text_content[:80] if entity.text_content else None,
        description=_describe_entity(entity),
    )


def _describe_entity(entity: EntityRef) -> str:
    """One-line description of an entity."""
    parts = [entity.entity_type.value]
    if entity.block_name:
        parts.append(f"block={entity.block_name}")
    if entity.text_content:
        excerpt = entity.text_content[:40]
        parts.append(f'"{excerpt}"')
    if entity.insert_point:
        parts.append(f"at ({entity.insert_point.x:.1f}, {entity.insert_point.y:.1f})")
    return " ".join(parts)



# _levenshtein_similarity and _levenshtein_distance moved to core/text_utils.py
