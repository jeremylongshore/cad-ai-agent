"""Shared text utilities — Levenshtein distance, entity description, evidence construction.

Extracted from scorer.py and repeated_condition.py to eliminate duplication
(ARCH-REVIEW-CAD-01 prerequisite P1).
"""

from __future__ import annotations

from ..models.cad_schema import EntityRef
from ..models.response_schema import EvidenceRef


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(
                min(
                    curr_row[j] + 1,
                    prev_row[j + 1] + 1,
                    prev_row[j] + cost,
                )
            )
        prev_row = curr_row

    return prev_row[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Levenshtein similarity ratio (0-1, where 1 = identical)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    max_len = max(len(s1), len(s2))
    distance = levenshtein_distance(s1, s2)
    return 1.0 - distance / max_len


def describe_entity(entity: EntityRef) -> str:
    """Canonical one-line description of an entity for evidence/explanations."""
    parts = [entity.entity_type.value]
    if entity.layer:
        parts.append(f"on layer '{entity.layer}'")
    if entity.text_content:
        preview = entity.text_content[:50]
        if len(entity.text_content) > 50:
            preview += "..."
        parts.append(f"text='{preview}'")
    if entity.block_name:
        parts.append(f"block='{entity.block_name}'")
    if entity.insert_point:
        parts.append(f"at ({entity.insert_point.x:.1f}, {entity.insert_point.y:.1f})")
    if entity.text_geometry:
        parts.append(f"provenance={entity.text_geometry.provenance.value}")
    return " ".join(parts)


def entity_to_evidence(entity: EntityRef) -> EvidenceRef:
    """Convert an EntityRef to an EvidenceRef for response payloads."""
    return EvidenceRef(
        entity_handle=entity.handle,
        layer=entity.layer,
        entity_type=entity.entity_type.value,
        description=describe_entity(entity),
        location=((entity.insert_point.x, entity.insert_point.y) if entity.insert_point else None),
        text_excerpt=(entity.text_content[:100] if entity.text_content else None),
    )
