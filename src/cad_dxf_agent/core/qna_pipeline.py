"""Deterministic Q&A pipeline — classify, build context, generate answer.

No LLM in the core path. Question classification uses keyword patterns.
Answer generation uses template-based formatting from entity/layer data.
"""

from __future__ import annotations

import re

from ..models.cad_schema import DrawingContext, EntityType
from ..models.qna_schema import QnaAnswer, QnaQuestionType, RegionContext
from ..models.region_schema import NormalizedRegion
from ..models.response_schema import EvidenceRef, PlatformResponse, ResponseType, TaskFamily
from .entity_index import EntityIndex
from .region_context import RegionContextBuilder

# ---------------------------------------------------------------------------
# Question classifier — keyword patterns
# ---------------------------------------------------------------------------

_QUESTION_PATTERNS: list[tuple[QnaQuestionType, list[re.Pattern[str]]]] = [
    (
        QnaQuestionType.LAYER_QUERY,
        [
            re.compile(r"\bwhat\b.*\b(?:on|in)\s+layer\b", re.I),
            re.compile(r"\bwhich\s+layer\b", re.I),
            re.compile(r"\blayer\s+\w+\s+(?:contain|ha[sv]e?|show)\b", re.I),
            re.compile(r"\blist\b.*\blayer\b", re.I),
            re.compile(r"\bentities?\s+on\s+layer\b", re.I),
        ],
    ),
    (
        QnaQuestionType.ENTITY_COUNT,
        [
            re.compile(r"\bhow\s+many\b", re.I),
            re.compile(r"\bcount\b.*\bentit", re.I),
            re.compile(r"\bnumber\s+of\b", re.I),
            re.compile(r"\btotal\b.*\bentit", re.I),
        ],
    ),
    (
        QnaQuestionType.TEXT_SEARCH,
        [
            re.compile(r"\bfind\b.*\btext\b", re.I),
            re.compile(r"\bsearch\b.*\btext\b", re.I),
            re.compile(r"\btext\b.*\bcontain", re.I),
            re.compile(r"\bwhere\b.*\bsay\b", re.I),
            re.compile(r'\bfind\b.*"[^"]+"', re.I),
            re.compile(r"\bfind\b.*'[^']+'", re.I),
        ],
    ),
    (
        QnaQuestionType.DIMENSION_QUERY,
        [
            re.compile(r"\bdimension", re.I),
            re.compile(r"\bmeasurement", re.I),
            re.compile(r"\bwhat\b.*\bsize\b", re.I),
        ],
    ),
    (
        QnaQuestionType.BLOCK_QUERY,
        [
            re.compile(r"\bblock", re.I),
            re.compile(r"\binsert(?:ion)?s?\b", re.I),
            re.compile(r"\bsymbol", re.I),
        ],
    ),
    (
        QnaQuestionType.ENTITY_LOOKUP,
        [
            re.compile(r"\bwhere\s+is\b", re.I),
            re.compile(r"\blocate\b", re.I),
            re.compile(r"\bfind\b(?!.*\btext\b)", re.I),
            re.compile(r"\bposition\s+of\b", re.I),
        ],
    ),
    (
        QnaQuestionType.ENTITY_LIST,
        [
            re.compile(r"\blist\b", re.I),
            re.compile(r"\bshow\b.*\bentit", re.I),
            re.compile(r"\bwhat\b.*\bentit", re.I),
            re.compile(r"\bwhat\s+is\b", re.I),
            re.compile(r"\bwhat\s+are\b", re.I),
        ],
    ),
    (
        QnaQuestionType.REGION_SUMMARY,
        [
            re.compile(r"\bwhat\b.*\b(?:here|this|region|area|section)\b", re.I),
            re.compile(r"\btell\s+me\b", re.I),
            re.compile(r"\bshow\s+me\b", re.I),
        ],
    ),
]


class QuestionClassifier:
    """Classify a natural-language question into QnaQuestionType."""

    def classify(self, prompt: str) -> QnaQuestionType:
        stripped = prompt.strip()
        if not stripped:
            return QnaQuestionType.REGION_SUMMARY

        for qtype, patterns in _QUESTION_PATTERNS:
            for pattern in patterns:
                if pattern.search(stripped):
                    return qtype

        return QnaQuestionType.REGION_SUMMARY


# ---------------------------------------------------------------------------
# Answer generator — template-based formatting
# ---------------------------------------------------------------------------


class AnswerGenerator:
    """Generate deterministic answers from RegionContext and question type."""

    def generate(self, qtype: QnaQuestionType, ctx: RegionContext, prompt: str) -> QnaAnswer:
        if ctx.entity_count == 0:
            return self._empty_answer(qtype, ctx)

        dispatch = {
            QnaQuestionType.ENTITY_LIST: self._entity_list,
            QnaQuestionType.TEXT_SEARCH: self._text_search,
            QnaQuestionType.LAYER_QUERY: self._layer_query,
            QnaQuestionType.REGION_SUMMARY: self._region_summary,
            QnaQuestionType.ENTITY_COUNT: self._entity_count,
            QnaQuestionType.DIMENSION_QUERY: self._dimension_query,
            QnaQuestionType.BLOCK_QUERY: self._block_query,
            QnaQuestionType.ENTITY_LOOKUP: self._entity_lookup,
        }
        handler = dispatch.get(qtype, self._region_summary)
        return handler(ctx, prompt)

    # --- Handlers ---

    def _entity_list(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        scope = "in the drawing" if ctx.is_whole_drawing else "in this region"
        lines = []
        evidence = []
        for ent in ctx.entities[:50]:
            desc = _describe_entity(ent)
            lines.append(f"  - {desc}")
            evidence.append(_evidence_from(ent))

        suffix = ""
        if ctx.entity_count > 50:
            suffix = f"\n({ctx.entity_count - 50} more not shown)"

        text = f"{ctx.entity_count} entity(ies) {scope}:\n" + "\n".join(lines) + suffix
        return QnaAnswer(
            question_type=QnaQuestionType.ENTITY_LIST,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=ctx.entity_count,
            region_context_summary=_context_summary(ctx),
        )

    def _text_search(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        # Extract search term from prompt
        term = _extract_search_term(prompt)
        if not term:
            return self._entity_list(ctx, prompt)

        matches = []
        for ent in ctx.text_entities:
            if ent.text_content and term.lower() in ent.text_content.lower():
                matches.append(ent)

        evidence = [_evidence_from(e) for e in matches[:20]]

        if not matches:
            text = f'No text containing "{term}" found.'
            confidence = ctx.confidence * 0.8
        else:
            lines = [f"  - {_describe_entity(e)}" for e in matches[:20]]
            suffix = f"\n({len(matches) - 20} more)" if len(matches) > 20 else ""
            header = f'Found {len(matches)} text entity(ies) containing "{term}":'
            text = f"{header}\n" + "\n".join(lines) + suffix
            confidence = ctx.confidence

        return QnaAnswer(
            question_type=QnaQuestionType.TEXT_SEARCH,
            answer_text=text,
            evidence=evidence,
            confidence=confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=len(matches),
            region_context_summary=_context_summary(ctx),
        )

    def _layer_query(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        # Extract layer name from prompt
        layer = _extract_layer_name(prompt, ctx.layers)

        if layer:
            count = ctx.layer_counts.get(layer, 0)
            ents = [e for e in ctx.entities if e.layer.upper() == layer.upper()]
            evidence = [_evidence_from(e) for e in ents[:20]]
            lines = [f"  - {_describe_entity(e)}" for e in ents[:20]]
            suffix = f"\n({count - 20} more)" if count > 20 else ""
            text = f"Layer {layer} has {count} entity(ies):\n" + "\n".join(lines) + suffix
        else:
            lines = [f"  - {ly}: {ctx.layer_counts[ly]} entity(ies)" for ly in ctx.layers]
            evidence = []
            text = f"{len(ctx.layers)} layer(s) with entities:\n" + "\n".join(lines)

        return QnaAnswer(
            question_type=QnaQuestionType.LAYER_QUERY,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=ctx.entity_count,
            region_context_summary=_context_summary(ctx),
        )

    def _region_summary(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        scope = "Drawing" if ctx.is_whole_drawing else "Region"
        parts = [
            f"{scope} contains {ctx.entity_count} entity(ies) across {len(ctx.layers)} layer(s)."
        ]

        if ctx.text_entities:
            parts.append(f"Text: {len(ctx.text_entities)} label(s).")
        if ctx.dimension_entities:
            parts.append(f"Dimensions: {len(ctx.dimension_entities)}.")
        if ctx.block_refs:
            names = ", ".join(ctx.block_names[:5]) if ctx.block_names else "unnamed"
            parts.append(f"Blocks: {len(ctx.block_refs)} ({names}).")
        if ctx.layers:
            parts.append(f"Layers: {', '.join(ctx.layers[:10])}.")

        evidence = [_evidence_from(e) for e in ctx.entities[:10]]
        return QnaAnswer(
            question_type=QnaQuestionType.REGION_SUMMARY,
            answer_text=" ".join(parts),
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=ctx.entity_count,
            region_context_summary=_context_summary(ctx),
        )

    def _entity_count(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        # Check if asking about a specific type or layer
        type_name = _extract_entity_type(prompt)
        layer_name = _extract_layer_name(prompt, ctx.layers)

        if type_name:
            upper_name = type_name.upper()
            type_match = [e for e in ctx.entities if e.entity_type.value.upper() == upper_name]
            count = len(type_match)
            text = f"There are {count} {type_name} entity(ies)."
            evidence = [_evidence_from(e) for e in type_match[:10]]
        elif layer_name:
            count = ctx.layer_counts.get(layer_name, 0)
            text = f"Layer {layer_name} has {count} entity(ies)."
            layer_match = [e for e in ctx.entities if e.layer.upper() == layer_name.upper()]
            evidence = [_evidence_from(e) for e in layer_match[:10]]
        else:
            text = f"There are {ctx.entity_count} entity(ies) total."
            evidence = [_evidence_from(e) for e in ctx.entities[:10]]
            count = ctx.entity_count

        return QnaAnswer(
            question_type=QnaQuestionType.ENTITY_COUNT,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=count,
            region_context_summary=_context_summary(ctx),
        )

    def _dimension_query(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        dims = ctx.dimension_entities
        if not dims:
            return QnaAnswer(
                question_type=QnaQuestionType.DIMENSION_QUERY,
                answer_text="No dimensions found in this context.",
                evidence=[],
                confidence=ctx.confidence * 0.8,
                ambiguity_flags=list(ctx.ambiguity_flags),
                entity_count=0,
                region_context_summary=_context_summary(ctx),
            )

        lines = [f"  - {_describe_entity(d)}" for d in dims[:20]]
        evidence = [_evidence_from(d) for d in dims[:20]]
        suffix = f"\n({len(dims) - 20} more)" if len(dims) > 20 else ""
        text = f"Found {len(dims)} dimension(s):\n" + "\n".join(lines) + suffix

        return QnaAnswer(
            question_type=QnaQuestionType.DIMENSION_QUERY,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=len(dims),
            region_context_summary=_context_summary(ctx),
        )

    def _block_query(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        blocks = ctx.block_refs
        if not blocks:
            return QnaAnswer(
                question_type=QnaQuestionType.BLOCK_QUERY,
                answer_text="No block references found in this context.",
                evidence=[],
                confidence=ctx.confidence * 0.8,
                ambiguity_flags=list(ctx.ambiguity_flags),
                entity_count=0,
                region_context_summary=_context_summary(ctx),
            )

        lines = [f"  - {_describe_entity(b)}" for b in blocks[:20]]
        evidence = [_evidence_from(b) for b in blocks[:20]]
        suffix = f"\n({len(blocks) - 20} more)" if len(blocks) > 20 else ""
        text = f"Found {len(blocks)} block reference(s):\n" + "\n".join(lines) + suffix
        if ctx.block_names:
            text += f"\nBlock types: {', '.join(ctx.block_names)}"

        return QnaAnswer(
            question_type=QnaQuestionType.BLOCK_QUERY,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=len(blocks),
            region_context_summary=_context_summary(ctx),
        )

    def _entity_lookup(self, ctx: RegionContext, prompt: str) -> QnaAnswer:
        # Try to extract a name/handle to look up
        term = _extract_search_term(prompt)
        if term:
            # Search by text content first, then by handle
            matches = [
                e
                for e in ctx.entities
                if (e.text_content and term.lower() in e.text_content.lower())
                or (e.block_name and term.lower() in e.block_name.lower())
                or e.handle.lower() == term.lower()
            ]
        else:
            matches = []

        if not matches:
            return QnaAnswer(
                question_type=QnaQuestionType.ENTITY_LOOKUP,
                answer_text=f'Could not locate "{term or "entity"}" in the current context.',
                evidence=[],
                confidence=ctx.confidence * 0.5,
                ambiguity_flags=list(ctx.ambiguity_flags) + ["entity_not_found"],
                entity_count=0,
                region_context_summary=_context_summary(ctx),
            )

        lines = [f"  - {_describe_entity(e)}" for e in matches[:10]]
        evidence = [_evidence_from(e) for e in matches[:10]]
        text = f'Found {len(matches)} match(es) for "{term}":\n' + "\n".join(lines)

        return QnaAnswer(
            question_type=QnaQuestionType.ENTITY_LOOKUP,
            answer_text=text,
            evidence=evidence,
            confidence=ctx.confidence,
            ambiguity_flags=list(ctx.ambiguity_flags),
            entity_count=len(matches),
            region_context_summary=_context_summary(ctx),
        )

    def _empty_answer(self, qtype: QnaQuestionType, ctx: RegionContext) -> QnaAnswer:
        scope = "the drawing" if ctx.is_whole_drawing else "this region"
        return QnaAnswer(
            question_type=qtype,
            answer_text=f"No entities found in {scope}.",
            evidence=[],
            confidence=0.0,
            ambiguity_flags=list(ctx.ambiguity_flags) + ["no_entities"],
            entity_count=0,
            region_context_summary=_context_summary(ctx),
        )


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class QnaPipeline:
    """Orchestrates question classification, context building, and answer generation.

    Returns PlatformResponse with response_type=ANSWER_ONLY.
    """

    def __init__(
        self,
        max_entities: int = 200,
        margin: float = 5.0,
    ) -> None:
        self._classifier = QuestionClassifier()
        self._context_builder = RegionContextBuilder(max_entities=max_entities, margin=margin)
        self._generator = AnswerGenerator()

    def answer(
        self,
        prompt: str,
        context: DrawingContext,
        region: NormalizedRegion | None = None,
        index: EntityIndex | None = None,
    ) -> PlatformResponse:
        qtype = self._classifier.classify(prompt)
        region_ctx = self._context_builder.build(context, region=region, index=index)

        # Empty context → needs_clarification
        if region_ctx.entity_count == 0 and not region_ctx.is_whole_drawing:
            return PlatformResponse(
                task_family=TaskFamily.QNA,
                response_type=ResponseType.NEEDS_CLARIFICATION,
                message="No entities found in the selected region. Try selecting a larger area.",
                confidence=0.0,
                ambiguity_flags=region_ctx.ambiguity_flags,
            )

        answer = self._generator.generate(qtype, region_ctx, prompt)

        return PlatformResponse(
            task_family=TaskFamily.QNA,
            response_type=ResponseType.ANSWER_ONLY,
            message=answer.answer_text,
            evidence=answer.evidence,
            confidence=answer.confidence,
            ambiguity_flags=answer.ambiguity_flags,
            data={
                "question_type": answer.question_type.value,
                "entity_count": answer.entity_count,
                "region_context_summary": answer.region_context_summary,
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _describe_entity(ent) -> str:
    """Build a human-readable one-liner for an entity."""
    parts = [ent.entity_type.value]
    if ent.block_name:
        parts.append(f'"{ent.block_name}"')
    if ent.text_content:
        excerpt = ent.text_content[:60]
        if len(ent.text_content) > 60:
            excerpt += "..."
        parts.append(f'"{excerpt}"')
    parts.append(f"on {ent.layer}")
    if ent.insert_point:
        parts.append(f"at ({ent.insert_point.x:.0f}, {ent.insert_point.y:.0f})")
    if ent.text_geometry:
        tg = ent.text_geometry
        if tg.effective_height is not None:
            parts.append(f"h={tg.effective_height}")
        if tg.rotation != 0.0:
            parts.append(f"rot={tg.rotation:.1f}")
    parts.append(f"[{ent.handle}]")
    return " ".join(parts)


def _evidence_from(ent) -> EvidenceRef:
    return EvidenceRef(
        entity_handle=ent.handle,
        layer=ent.layer,
        entity_type=ent.entity_type.value,
        description=_describe_entity(ent),
        text_excerpt=ent.text_content[:100] if ent.text_content else None,
        location=(ent.insert_point.x, ent.insert_point.y) if ent.insert_point else None,
    )


def _context_summary(ctx: RegionContext) -> dict:
    return {
        "entity_count": ctx.entity_count,
        "layer_count": len(ctx.layers),
        "text_count": len(ctx.text_entities),
        "dimension_count": len(ctx.dimension_entities),
        "block_count": len(ctx.block_refs),
        "is_whole_drawing": ctx.is_whole_drawing,
    }


def _extract_search_term(prompt: str) -> str | None:
    """Extract a quoted or keyword search term from a prompt."""
    # Quoted string
    m = re.search(r'"([^"]+)"', prompt) or re.search(r"'([^']+)'", prompt)
    if m:
        return m.group(1)

    # After "find", "search", "locate", "where is"
    m = re.search(
        r"\b(?:find|search\s+for|locate|where\s+is|position\s+of)\s+(.+?)(?:\s+(?:on|in|at|from)\b|[?.]|$)",
        prompt,
        re.I,
    )
    if m:
        term = m.group(1).strip()
        # Remove common filler
        term = re.sub(r"^(?:the|a|an|any|all)\s+", "", term, flags=re.I)
        if term and term.lower() not in {"text", "entity", "entities", "block", "blocks"}:
            return term

    return None


def _extract_layer_name(prompt: str, available_layers: list[str]) -> str | None:
    """Extract a layer name from the prompt."""
    # Match "layer X" or "on layer X"
    m = re.search(r"\blayer\s+(\w+)", prompt, re.I)
    if m:
        candidate = m.group(1).upper()
        # Check if it matches an available layer
        for layer in available_layers:
            if layer.upper() == candidate:
                return layer
        return candidate  # Return even if not in current context

    # Check if any known layer name appears in the prompt
    prompt_upper = prompt.upper()
    for layer in available_layers:
        if layer.upper() in prompt_upper:
            return layer

    return None


def _extract_entity_type(prompt: str) -> str | None:
    """Extract an entity type name from the prompt."""
    type_names = {t.value.upper(): t.value for t in EntityType}
    prompt_upper = prompt.upper()
    for key, val in type_names.items():
        if key in prompt_upper:
            return val
    # Common aliases
    aliases = {"LINES": "LINE", "TEXTS": "TEXT", "BLOCKS": "INSERT", "INSERTS": "INSERT"}
    for alias, canonical in aliases.items():
        if alias in prompt_upper:
            return canonical
    return None
