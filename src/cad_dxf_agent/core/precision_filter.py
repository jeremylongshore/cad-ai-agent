"""Precision filter — entity scope narrowing and deterministic overrides (EPIC-CAD-14).

Parses PrecisionControls from client_metadata, applies entity filters using
EntityIndex, overrides move deltas, and builds structured action details.
"""

from __future__ import annotations

from typing import Any

from ..models.cad_schema import DrawingContext, EntityRef
from ..models.ops_schema import ChangeSet, EditOperation, OpType
from ..models.precision_schema import (
    ActionDetail,
    ActionStatus,
    MatchCandidate,
    PrecisionControls,
)


def parse_precision_controls(client_metadata: dict[str, Any] | None) -> PrecisionControls | None:
    """Extract PrecisionControls from client_metadata.precision, or None."""
    if not client_metadata:
        return None
    precision_data = client_metadata.get("precision")
    if not precision_data or not isinstance(precision_data, dict):
        return None
    return PrecisionControls(**precision_data)


def apply_entity_filter(
    entities: list[EntityRef],
    controls: PrecisionControls,
) -> list[EntityRef]:
    """Filter entities through the precision control chain.

    Order: target_handles → target_layers → exclude_layers → target_types → model_space_only.
    Each filter narrows the set. An empty filter list means "no restriction" for that axis.
    """
    result = list(entities)

    # Handle targeting — if specified, only include matching handles
    if controls.target_handles:
        handle_set = set(controls.target_handles)
        result = [e for e in result if e.handle in handle_set]

    # Layer inclusion — if specified, only include entities on these layers
    if controls.target_layers:
        layer_set = {layer.upper() for layer in controls.target_layers}
        result = [e for e in result if e.layer.upper() in layer_set]

    # Layer exclusion — remove entities on these layers
    if controls.exclude_layers:
        exclude_set = {layer.upper() for layer in controls.exclude_layers}
        result = [e for e in result if e.layer.upper() not in exclude_set]

    # Type filtering — if specified, only include matching types
    if controls.target_types:
        type_set = {t.upper() for t in controls.target_types}
        result = [e for e in result if e.entity_type.value.upper() in type_set]

    # Model space only
    if controls.model_space_only:
        result = [e for e in result if e.space == "Model"]

    return result


def apply_exact_delta(
    operations: list[EditOperation],
    exact_delta: dict[str, float],
) -> list[EditOperation]:
    """Override dx/dy in move operations with exact values.

    Only affects move_entity ops. Non-move ops pass through unchanged.
    Returns a new list — does not mutate input operations.
    """
    result = []
    for op in operations:
        if op.op_type == OpType.MOVE_ENTITY:
            new_params = dict(op.params)
            if "dx" in exact_delta:
                new_params["dx"] = exact_delta["dx"]
            if "dy" in exact_delta:
                new_params["dy"] = exact_delta["dy"]
            result.append(op.model_copy(update={"params": new_params}))
        else:
            result.append(op)
    return result


def check_confidence_threshold(confidence: float, threshold: float) -> bool:
    """Return True if confidence meets or exceeds the threshold."""
    return confidence >= threshold


def build_match_candidates(
    entities: list[EntityRef],
    controls: PrecisionControls,
    *,
    max_candidates: int = 10,
) -> list[MatchCandidate]:
    """Build ranked match candidates when targeting is ambiguous.

    Ranks by relevance: entities matching more criteria score higher.
    """
    candidates: list[tuple[float, MatchCandidate]] = []

    for entity in entities[: max_candidates * 5]:  # scan up to 5x max to find best
        score = 0.0
        reasons: list[str] = []

        # Handle match boost (exact match — highest priority)
        if controls.target_handles and entity.handle in controls.target_handles:
            score += 1.0
            reasons.append("exact_handle")

        # Layer match boost
        if controls.target_layers and entity.layer.upper() in {
            layer.upper() for layer in controls.target_layers
        }:
            score += 0.4
            reasons.append(f"layer={entity.layer}")

        # Type match boost
        if controls.target_types and entity.entity_type.value.upper() in {
            t.upper() for t in controls.target_types
        }:
            score += 0.3
            reasons.append(f"type={entity.entity_type.value}")

        # Model space boost
        if controls.model_space_only and entity.space == "Model":
            score += 0.1
            reasons.append("model_space")

        # Base score if no criteria matched but entity exists
        if not reasons:
            score = 0.1
            reasons.append("default")

        location = None
        if entity.insert_point:
            location = (entity.insert_point.x, entity.insert_point.y)

        candidates.append(
            (
                score,
                MatchCandidate(
                    handle=entity.handle,
                    layer=entity.layer,
                    entity_type=entity.entity_type.value,
                    confidence=min(score, 1.0),
                    match_reason=", ".join(reasons),
                    location=location,
                ),
            )
        )

    # Sort by score descending, take top N
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [mc for _, mc in candidates[:max_candidates]]


def build_action_details(
    changeset: ChangeSet,
    context: DrawingContext,
    validation: Any | None = None,
) -> list[ActionDetail]:
    """Build per-entity action details from changeset + context + validation.

    Maps each operation to an ActionDetail with before/after state,
    status derived from validation blockers, and evidence.
    """
    # Build set of blocked handles from validation using operation_index
    blocked_handles: set[str] = set()
    if validation and hasattr(validation, "blockers"):
        for blocker in validation.blockers:
            idx = getattr(blocker, "operation_index", None)
            if idx is not None and 0 <= idx < len(changeset.operations):
                handle = changeset.operations[idx].target_handle
                if handle:
                    blocked_handles.add(handle)

    details: list[ActionDetail] = []
    for op in changeset.operations:
        handle = op.target_handle or ""
        entity = context.get_entity_by_handle(handle) if handle else None

        # Build before state from entity
        before: dict[str, Any] = {}
        if entity:
            if entity.insert_point:
                before["x"] = entity.insert_point.x
                before["y"] = entity.insert_point.y
            if entity.text_content:
                before["text"] = entity.text_content

        # Build after state from params
        after: dict[str, Any] = {}
        if op.op_type == OpType.MOVE_ENTITY:
            dx = op.params.get("dx", 0)
            dy = op.params.get("dy", 0)
            if entity and entity.insert_point:
                after["x"] = entity.insert_point.x + dx
                after["y"] = entity.insert_point.y + dy
            else:
                after["dx"] = dx
                after["dy"] = dy
        elif op.op_type == OpType.EDIT_TEXT:
            after["text"] = op.params.get("new_text", "")
        elif op.op_type == OpType.ADD_BLOCK:
            after["block_name"] = op.params.get("block_name", "")
            insert_pt = op.params.get("insert_point", {})
            if isinstance(insert_pt, dict):
                after["x"] = insert_pt.get("x", 0)
                after["y"] = insert_pt.get("y", 0)

        # Determine status
        status = ActionStatus.BLOCKED if handle in blocked_handles else ActionStatus.PLANNED

        # Evidence
        evidence: list[str] = []
        if entity:
            evidence.append(f"entity on layer {entity.layer}")
            if entity.text_content:
                evidence.append(f'text: "{entity.text_content[:50]}"')

        details.append(
            ActionDetail(
                entity_handle=handle,
                entity_type=entity.entity_type.value if entity else "UNKNOWN",
                layer=entity.layer if entity else (op.target_layer or ""),
                action=op.op_type.value,
                before=before,
                after=after,
                status=status,
                confidence=1.0,
                evidence=evidence,
            )
        )

    return details
