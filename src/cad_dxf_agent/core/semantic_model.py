"""Semantic model — builds context summaries for the LLM planner.

Includes family-aware context building (EPIC-CAD-13 Area 1) that enriches
the planner context with document family hint and shared primitives.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..models.cad_schema import DrawingContext, EntityRef
from ..otel import get_tracer

tracer = get_tracer(__name__)


ENTITY_CAP = 500
"""Maximum entities included in verbose planner context.

Real-world DXF files can have thousands of entities, producing millions of
tokens when serialised as JSON.  Cap at 500 to stay safely within LLM
context limits (~1M tokens for Gemini).
"""


def build_planner_context(context: DrawingContext) -> dict:
    """Build a JSON-serializable summary of the drawing for the LLM planner.

    This is the information the planner sees to make targeting decisions.
    It does NOT include raw DXF data. Includes all spaces (model + layouts).

    If the drawing has more than *ENTITY_CAP* entities the list is truncated
    and ``entities_truncated`` / ``total_entity_count`` fields are added.
    """
    with tracer.start_as_current_span("cad.build_context") as span:
        span.set_attribute("cad.entities.count", context.entity_count)

        layer_summary = [
            {
                "name": layer.name,
                "protected": layer.protected,
                "entity_count": sum(
                    1 for e in context.entities if e.layer.upper() == layer.name.upper()
                ),
            }
            for layer in context.layers
        ]

        entities = context.entities
        truncated = len(entities) > ENTITY_CAP
        if truncated:
            entities = entities[:ENTITY_CAP]

        entity_summary = [_entity_to_summary(e) for e in entities]

        layout_summary = [
            {"name": layout.name, "entity_count": layout.entity_count} for layout in context.layouts
        ]

        result = {
            "file_path": context.file_path,
            "entity_count": context.entity_count,
            "layers": layer_summary,
            "entities": entity_summary,
            "blocks": context.blocks,
            "layouts": layout_summary,
            "unsupported_types": context.unsupported_entity_types,
        }

        if truncated:
            result["entities_truncated"] = True
            result["total_entity_count"] = context.entity_count
            span.set_attribute("cad.entities.truncated", True)

        return result


def _entity_to_summary(e: EntityRef) -> dict:
    """Build a JSON-serializable summary dict for a single entity."""
    d: dict = {
        "handle": e.handle,
        "type": e.entity_type.value,
        "layer": e.layer,
        "space": e.space,
        "insert_point": (
            {"x": e.insert_point.x, "y": e.insert_point.y} if e.insert_point else None
        ),
        "text": e.text_content,
        "block_name": e.block_name,
    }
    if e.text_geometry is not None:
        tg = e.text_geometry
        d["text_geometry"] = {
            "height": tg.height,
            "rotation": tg.rotation,
            "provenance": tg.provenance.value,
        }
    return d


def build_compact_context(context: DrawingContext) -> str:
    """Build a compact text summary for the LLM agent's initial prompt.

    Instead of dumping all entity JSON, provides a high-level overview
    so the agent uses query tools (find_entities, find_nearest) to
    discover specific entities before acting.
    """
    counts_by_layer: Counter[str] = Counter()
    counts_by_type: Counter[str] = Counter()
    text_labels: list[str] = []

    for entity in context.entities:
        counts_by_layer[entity.layer] += 1
        counts_by_type[entity.entity_type.value] += 1
        if entity.text_content:
            text_labels.append(entity.text_content)

    protected = context.get_protected_layers()

    lines = [
        "DRAWING SUMMARY:",
        f"- File: {Path(context.file_path).name}",
        f"- Total entities: {context.entity_count}",
        f"- Entity types: {', '.join(f'{t}({n})' for t, n in counts_by_type.most_common())}",
        "- Layers:",
    ]

    for layer in context.layers:
        count = counts_by_layer.get(layer.name, 0)
        prot = " (PROTECTED)" if layer.name in protected else ""
        lines.append(f"    {layer.name}: {count} entities{prot}")

    if context.blocks:
        lines.append(f"- Blocks available: {', '.join(context.blocks)}")

    if context.layouts:
        layout_desc = ", ".join(f"{lay.name}({lay.entity_count})" for lay in context.layouts)
        lines.append(f"- Layouts: {layout_desc}")

    if text_labels:
        sample = text_labels[:5]
        lines.append(f"- Sample text labels: {sample}")

    lines.append("")
    lines.append(
        "Use find_entities(), get_entity(), find_nearest() tools to query specific entities."
    )
    lines.append("Do NOT guess entity handles — always search first.")

    return "\n".join(lines)


def build_enriched_context(context: DrawingContext) -> dict:
    """Build family-aware enriched context for the objective pipeline.

    Extends the standard planner context with:
    - document_family: detected DocumentFamilyHint with confidence
    - primitives: shared primitive summary (symbols, labels, layer classification)

    This is used by the stage pipeline executor, not the legacy planner.
    """
    from ..core.family_detector import detect_document_family
    from ..core.primitive_extractors import extract_primitives

    with tracer.start_as_current_span("cad.build_enriched_context") as span:
        # Base planner context
        base = build_planner_context(context)

        # Document family detection
        family_result = detect_document_family(context)
        base["document_family"] = {
            "family": family_result.family.value,
            "confidence": family_result.confidence,
            "signal_count": family_result.signal_count,
            "top_signals": family_result.top_signals,
            "runner_up": (family_result.runner_up.value if family_result.runner_up else None),
        }

        # Shared primitives
        primitives = extract_primitives(context)
        base["primitives"] = {
            "symbols": {
                "total_inserts": primitives.symbols.total_inserts,
                "unique_blocks": primitives.symbols.unique_blocks,
                "top_blocks": dict(list(primitives.symbols.counts_by_block.items())[:10]),
            },
            "labels": {
                "total_labels": primitives.labels.total_labels,
                "unique_texts": primitives.labels.unique_texts,
                "sample_texts": primitives.labels.sample_texts[:10],
            },
            "layer_classification": {
                "structural": primitives.layer_classification.structural,
                "annotation": primitives.layer_classification.annotation,
                "dimension": primitives.layer_classification.dimension,
                "title_border": primitives.layer_classification.title_border,
                "mep": primitives.layer_classification.mep,
                "other_count": len(primitives.layer_classification.other),
            },
            "entity_counts": primitives.entity_counts,
        }

        span.set_attribute("cad.document_family", family_result.family.value)
        span.set_attribute("cad.family_confidence", family_result.confidence)

        return base
