"""Shared primitive extractors — extract universal drawing primitives.

These primitives appear across ALL 20 document families:
- Symbol/block counts by category
- Schedule/table detection (INSERT blocks with tabular attributes)
- Label/note extraction (text entities grouped by purpose)
- Layer classification (structural, annotation, dimension, etc.)

Each extractor returns a simple dict/list — no family-specific logic.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType


@dataclass
class SymbolSummary:
    """Summary of block/symbol usage across the drawing."""

    total_inserts: int = 0
    unique_blocks: int = 0
    counts_by_block: dict[str, int] = field(default_factory=dict)
    counts_by_layer: dict[str, int] = field(default_factory=dict)


@dataclass
class LabelSummary:
    """Summary of text labels/notes in the drawing."""

    total_labels: int = 0
    by_layer: dict[str, list[str]] = field(default_factory=dict)
    unique_texts: int = 0
    sample_texts: list[str] = field(default_factory=list)


@dataclass
class LayerClassification:
    """Classification of layers by their apparent purpose."""

    structural: list[str] = field(default_factory=list)
    annotation: list[str] = field(default_factory=list)
    dimension: list[str] = field(default_factory=list)
    title_border: list[str] = field(default_factory=list)
    mep: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)


@dataclass
class DrawingPrimitives:
    """Aggregated shared primitives extracted from any drawing."""

    symbols: SymbolSummary
    labels: LabelSummary
    layer_classification: LayerClassification
    entity_counts: dict[str, int]
    total_entities: int


def extract_primitives(context: DrawingContext) -> DrawingPrimitives:
    """Extract all shared primitives from a drawing context."""
    return DrawingPrimitives(
        symbols=extract_symbols(context),
        labels=extract_labels(context),
        layer_classification=classify_layers(context),
        entity_counts=count_entities_by_type(context),
        total_entities=context.entity_count,
    )


def extract_symbols(context: DrawingContext) -> SymbolSummary:
    """Extract block/symbol usage summary."""
    block_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()

    for entity in context.entities:
        if entity.entity_type == EntityType.INSERT and entity.block_name:
            block_counts[entity.block_name] += 1
            layer_counts[entity.layer] += 1

    return SymbolSummary(
        total_inserts=sum(block_counts.values()),
        unique_blocks=len(block_counts),
        counts_by_block=dict(block_counts.most_common()),
        counts_by_layer=dict(layer_counts.most_common()),
    )


def extract_labels(
    context: DrawingContext,
    *,
    max_samples: int = 20,
) -> LabelSummary:
    """Extract text labels/notes grouped by layer."""
    by_layer: dict[str, list[str]] = {}
    unique: set[str] = set()
    samples: list[str] = []

    for entity in context.entities:
        if entity.entity_type not in (EntityType.TEXT, EntityType.MTEXT):
            continue
        text = entity.text_content
        if not text or not text.strip():
            continue

        clean = text.strip()
        layer = entity.layer
        by_layer.setdefault(layer, []).append(clean)
        unique.add(clean)

        if len(samples) < max_samples and clean not in samples:
            samples.append(clean)

    total = sum(len(v) for v in by_layer.values())
    return LabelSummary(
        total_labels=total,
        by_layer=by_layer,
        unique_texts=len(unique),
        sample_texts=samples,
    )


# Layer classification patterns
_STRUCTURAL_PATTERNS = re.compile(
    r"wall|column|beam|struct|frame|found|slab|grid|brace",
    re.IGNORECASE,
)
_ANNOTATION_PATTERNS = re.compile(
    r"note|anno|text|label|tag|callout|keynote|legend",
    re.IGNORECASE,
)
_DIMENSION_PATTERNS = re.compile(
    r"dim|dimension|measure",
    re.IGNORECASE,
)
_TITLE_PATTERNS = re.compile(
    r"title|border|sheet|viewport|seal|stamp|revision",
    re.IGNORECASE,
)
_MEP_PATTERNS = re.compile(
    r"elec|mech|plumb|hvac|fire|sprink|pipe|duct|panel|light"
    r"|^[EeMmPp]-",  # AIA layer prefixes: E-, M-, P-
    re.IGNORECASE,
)


def classify_layers(context: DrawingContext) -> LayerClassification:
    """Classify layers by their apparent purpose based on naming patterns."""
    result = LayerClassification()

    for layer in context.layers:
        name = layer.name
        if _STRUCTURAL_PATTERNS.search(name):
            result.structural.append(name)
        elif _ANNOTATION_PATTERNS.search(name):
            result.annotation.append(name)
        elif _DIMENSION_PATTERNS.search(name):
            result.dimension.append(name)
        elif _TITLE_PATTERNS.search(name):
            result.title_border.append(name)
        elif _MEP_PATTERNS.search(name):
            result.mep.append(name)
        else:
            result.other.append(name)

    return result


def count_entities_by_type(context: DrawingContext) -> dict[str, int]:
    """Count entities by EntityType."""
    counts: Counter[str] = Counter()
    for entity in context.entities:
        counts[entity.entity_type.value] += 1
    return dict(counts.most_common())
