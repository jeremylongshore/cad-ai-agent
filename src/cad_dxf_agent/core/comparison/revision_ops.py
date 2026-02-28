"""Convert EntityChange items into reversible RevisionOp sequences."""

from __future__ import annotations

import uuid

from ...models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    EntityChange,
    RevisionOp,
    RevisionOpType,
)


def entity_change_to_ops(change: EntityChange, change_index: int) -> list[RevisionOp]:
    """Convert a single EntityChange into one or more RevisionOps.

    UNCHANGED changes produce no ops.  A single MODIFIED change may emit
    multiple ops (text + geometry + attributes).
    """
    if change.category == ChangeCategory.UNCHANGED:
        return []

    if change.category == ChangeCategory.MOVED:
        return _ops_for_moved(change, change_index)
    if change.category == ChangeCategory.REMOVED:
        return _ops_for_removed(change, change_index)
    if change.category == ChangeCategory.ADDED:
        return _ops_for_added(change, change_index)
    if change.category == ChangeCategory.MODIFIED:
        return _ops_for_modified(change, change_index)

    return []  # pragma: no cover


def comparison_result_to_ops(result: ComparisonResult) -> list[RevisionOp]:
    """Convert all changes in a ComparisonResult to RevisionOps."""
    ops: list[RevisionOp] = []
    for idx, change in enumerate(result.changes):
        ops.extend(entity_change_to_ops(change, idx))
    return ops


# --- Private helpers ---


def _make_id() -> str:
    return uuid.uuid4().hex[:8]


def _snapshot_dict(snap) -> dict:
    """Serialize a GeometrySnapshot to a dict for forward/reverse payloads."""
    return {
        "handle": snap.handle,
        "entity_type": snap.entity_type.value,
        "layer": snap.layer,
        "points": [{"x": p.x, "y": p.y} for p in snap.points],
        "text_content": snap.text_content,
        "block_name": snap.block_name,
        "attributes": dict(snap.attributes),
    }


def _ops_for_moved(change: EntityChange, change_index: int) -> list[RevisionOp]:
    assert change.master_snapshot is not None
    assert change.displacement is not None
    dx, dy = change.displacement.x, change.displacement.y
    return [
        RevisionOp(
            op_id=_make_id(),
            op_type=RevisionOpType.MOVE,
            change_index=change_index,
            target_handle=change.master_snapshot.handle,
            target_layer=change.master_snapshot.layer,
            forward={"dx": dx, "dy": dy},
            reverse={"dx": -dx, "dy": -dy},
            confidence=change.confidence,
            match_method=change.match_method,
            description=(
                f"Move {change.master_snapshot.entity_type} "
                f"on {change.master_snapshot.layer} by ({dx}, {dy})"
            ),
        )
    ]


def _ops_for_removed(change: EntityChange, change_index: int) -> list[RevisionOp]:
    assert change.master_snapshot is not None
    return [
        RevisionOp(
            op_id=_make_id(),
            op_type=RevisionOpType.DELETE,
            change_index=change_index,
            target_handle=change.master_snapshot.handle,
            target_layer=change.master_snapshot.layer,
            forward={},
            reverse={"snapshot": _snapshot_dict(change.master_snapshot)},
            confidence=change.confidence,
            match_method=change.match_method,
            description=(
                f"Delete {change.master_snapshot.entity_type} on {change.master_snapshot.layer}"
            ),
        )
    ]


def _ops_for_added(change: EntityChange, change_index: int) -> list[RevisionOp]:
    assert change.revision_snapshot is not None
    return [
        RevisionOp(
            op_id=_make_id(),
            op_type=RevisionOpType.ADD,
            change_index=change_index,
            target_handle=change.revision_snapshot.handle,
            target_layer=change.revision_snapshot.layer,
            forward={"snapshot": _snapshot_dict(change.revision_snapshot)},
            reverse={},
            confidence=change.confidence,
            match_method=change.match_method,
            description=(
                f"Add {change.revision_snapshot.entity_type} on {change.revision_snapshot.layer}"
            ),
        )
    ]


def _ops_for_modified(change: EntityChange, change_index: int) -> list[RevisionOp]:
    assert change.master_snapshot is not None
    assert change.revision_snapshot is not None
    mods = change.modifications or {}
    ops: list[RevisionOp] = []

    # Text modification
    if "text_content" in mods:
        mod = mods["text_content"]
        ops.append(
            RevisionOp(
                op_id=_make_id(),
                op_type=RevisionOpType.MODIFY_TEXT,
                change_index=change_index,
                target_handle=change.master_snapshot.handle,
                target_layer=change.master_snapshot.layer,
                forward={"new_text": mod["to"]},
                reverse={"new_text": mod["from"]},
                confidence=change.confidence,
                match_method=change.match_method,
                description=f"Change text from {mod['from']!r} to {mod['to']!r}",
            )
        )

    # Geometry modification (point changes)
    geom_keys = {"point_count", "changed_point_indices"}
    if geom_keys & mods.keys():
        ops.append(
            RevisionOp(
                op_id=_make_id(),
                op_type=RevisionOpType.MODIFY_GEOMETRY,
                change_index=change_index,
                target_handle=change.master_snapshot.handle,
                target_layer=change.master_snapshot.layer,
                forward={
                    "new_points": [{"x": p.x, "y": p.y} for p in change.revision_snapshot.points]
                },
                reverse={
                    "new_points": [{"x": p.x, "y": p.y} for p in change.master_snapshot.points]
                },
                confidence=change.confidence,
                match_method=change.match_method,
                description=f"Modify geometry on {change.master_snapshot.layer}",
            )
        )

    # Attribute modifications (radius, angles, etc.)
    attrib_keys = {"radius", "start_angle", "end_angle", "ratio"}
    found_attribs = attrib_keys & mods.keys()
    if found_attribs:
        fwd = {k: mods[k]["to"] for k in found_attribs}
        rev = {k: mods[k]["from"] for k in found_attribs}
        ops.append(
            RevisionOp(
                op_id=_make_id(),
                op_type=RevisionOpType.MODIFY_ATTRIBUTES,
                change_index=change_index,
                target_handle=change.master_snapshot.handle,
                target_layer=change.master_snapshot.layer,
                forward=fwd,
                reverse=rev,
                confidence=change.confidence,
                match_method=change.match_method,
                description=(
                    f"Modify attributes ({', '.join(sorted(found_attribs))}) "
                    f"on {change.master_snapshot.layer}"
                ),
            )
        )

    return ops
