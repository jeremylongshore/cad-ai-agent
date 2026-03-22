"""Validator engine — checks operations against rules before apply."""

from __future__ import annotations

import math

from ..models.cad_schema import DrawingContext
from ..models.changes_schema import ValidationResult
from ..models.config_schema import RuleConfig
from ..models.ops_schema import ChangeSet, EditOperation, OpType
from ..otel import get_tracer
from .entity_index import EntityIndex

tracer = get_tracer(__name__)

# Operations that create new entities (no target_handle needed)
_CREATION_OPS = frozenset(
    {
        OpType.ADD_BLOCK,
        OpType.ADD_LINE,
        OpType.ADD_POLYLINE,
        OpType.ADD_CIRCLE,
        OpType.ADD_ARC,
        OpType.ADD_TEXT,
    }
)


def validate_changeset(
    changeset: ChangeSet,
    context: DrawingContext,
    rules: RuleConfig,
) -> ValidationResult:
    """Validate all operations in a changeset against drawing context and rules.

    Returns a ValidationResult with blockers and warnings.
    Blockers prevent apply; warnings are informational.
    """
    with tracer.start_as_current_span("cad.validate") as span:
        span.set_attribute("cad.ops.count", changeset.op_count)

        result = ValidationResult()
        index = context.index
        protected_upper = [layer.upper() for layer in rules.protected_layers]

        for i, op in enumerate(changeset.operations):
            _validate_operation(op, i, index, protected_upper, rules, result)

        span.set_attribute("cad.validation.valid", result.valid)
        span.set_attribute("cad.validation.blockers", len(result.blockers))

        return result


def _validate_operation(
    op: EditOperation,
    index_pos: int,
    entity_index: EntityIndex,
    protected_layers: list[str],
    rules: RuleConfig,
    result: ValidationResult,
) -> None:
    """Validate a single operation."""
    # Check op type is supported
    if op.op_type not in OpType:
        result.add_blocker(f"Unsupported operation type: {op.op_type}", index_pos)
        return

    # For creation ops, no target entity needed
    if op.op_type in _CREATION_OPS:
        _validate_creation_op(op, index_pos, protected_layers, rules, result)
        return

    # All other ops need a target handle
    if not op.target_handle:
        result.add_blocker("Operation requires target_handle", index_pos)
        return

    entity = entity_index.get_by_handle(op.target_handle)
    if entity is None:
        result.add_blocker(
            f"Target entity not found: {op.target_handle}",
            index_pos,
        )
        return

    # Protected layer check
    if entity.layer.upper() in protected_layers:
        result.add_blocker(
            f"Cannot edit entity on protected layer: {entity.layer}",
            index_pos,
        )
        return

    # Operation-specific validation
    if op.op_type == OpType.MOVE_ENTITY:
        _validate_move(op, index_pos, rules, result)
    elif op.op_type == OpType.EDIT_TEXT:
        _validate_edit_text(op, index_pos, result)
    elif op.op_type == OpType.ROTATE_ENTITY:
        _validate_rotate(op, index_pos, result)
    elif op.op_type == OpType.COPY_ENTITY:
        _validate_copy(op, index_pos, result)
    elif op.op_type == OpType.SCALE_ENTITY:
        _validate_scale(op, index_pos, result)
    elif op.op_type == OpType.MIRROR_ENTITY:
        _validate_mirror(op, index_pos, result)


# --- V1 operation validators ---


def _validate_move(
    op: EditOperation,
    index_pos: int,
    rules: RuleConfig,
    result: ValidationResult,
) -> None:
    """Validate move_entity parameters."""
    dx = op.params.get("dx")
    dy = op.params.get("dy")
    if dx is None or dy is None:
        result.add_blocker("move_entity requires dx and dy params", index_pos)
        return

    if not isinstance(dx, (int, float)) or not isinstance(dy, (int, float)):
        result.add_blocker("dx and dy must be numeric", index_pos)
        return

    if math.isnan(dx) or math.isnan(dy) or math.isinf(dx) or math.isinf(dy):
        result.add_blocker("dx/dy contains NaN or Inf", index_pos)
        return

    if rules.max_move_distance is not None:
        distance = math.sqrt(dx**2 + dy**2)
        if distance > rules.max_move_distance:
            result.add_warning(
                f"Move distance {distance:.2f} exceeds max {rules.max_move_distance}",
                index_pos,
            )


def _validate_edit_text(
    op: EditOperation,
    index_pos: int,
    result: ValidationResult,
) -> None:
    """Validate edit_text parameters."""
    new_text = op.params.get("new_text")
    if new_text is None:
        result.add_blocker("edit_text requires new_text param", index_pos)
        return

    if not isinstance(new_text, str):
        result.add_blocker("new_text must be a string", index_pos)
        return


# --- V2 transform validators ---


def _validate_rotate(
    op: EditOperation,
    index_pos: int,
    result: ValidationResult,
) -> None:
    """Validate rotate_entity parameters."""
    angle = op.params.get("angle")
    if angle is None:
        result.add_blocker("rotate_entity requires angle param", index_pos)
        return

    if not isinstance(angle, (int, float)):
        result.add_blocker("angle must be numeric", index_pos)
        return

    if math.isnan(angle) or math.isinf(angle):
        result.add_blocker("angle contains NaN or Inf", index_pos)
        return


def _validate_copy(
    op: EditOperation,
    index_pos: int,
    result: ValidationResult,
) -> None:
    """Validate copy_entity parameters."""
    dx = op.params.get("dx")
    dy = op.params.get("dy")
    if dx is None or dy is None:
        result.add_blocker("copy_entity requires dx and dy params", index_pos)
        return

    if not isinstance(dx, (int, float)) or not isinstance(dy, (int, float)):
        result.add_blocker("dx and dy must be numeric", index_pos)
        return

    if math.isnan(dx) or math.isnan(dy) or math.isinf(dx) or math.isinf(dy):
        result.add_blocker("dx/dy contains NaN or Inf", index_pos)
        return


def _validate_scale(
    op: EditOperation,
    index_pos: int,
    result: ValidationResult,
) -> None:
    """Validate scale_entity parameters."""
    factor = op.params.get("factor")
    if factor is None:
        result.add_blocker("scale_entity requires factor param", index_pos)
        return

    if not isinstance(factor, (int, float)):
        result.add_blocker("factor must be numeric", index_pos)
        return

    if math.isnan(factor) or math.isinf(factor):
        result.add_blocker("factor contains NaN or Inf", index_pos)
        return

    if factor == 0:
        result.add_blocker("scale factor cannot be zero", index_pos)
        return

    if factor < 0:
        result.add_warning("Negative scale factor will mirror the entity", index_pos)


def _validate_mirror(
    op: EditOperation,
    index_pos: int,
    result: ValidationResult,
) -> None:
    """Validate mirror_entity parameters."""
    axis = op.params.get("axis")
    if axis is None:
        result.add_blocker("mirror_entity requires axis param", index_pos)
        return

    if axis not in ("x", "y"):
        result.add_blocker("axis must be 'x' or 'y'", index_pos)
        return

    value = op.params.get("value")
    if value is not None:
        if not isinstance(value, (int, float)):
            result.add_blocker("mirror value must be numeric", index_pos)
            return
        if math.isnan(value) or math.isinf(value):
            result.add_blocker("mirror value contains NaN or Inf", index_pos)
            return


# --- Creation operation validators ---


def _validate_creation_op(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    rules: RuleConfig,
    result: ValidationResult,
) -> None:
    """Validate entity creation operations."""
    if op.op_type == OpType.ADD_BLOCK:
        _validate_add_block(op, index_pos, protected_layers, rules, result)
    elif op.op_type == OpType.ADD_LINE:
        _validate_add_line(op, index_pos, protected_layers, result)
    elif op.op_type == OpType.ADD_POLYLINE:
        _validate_add_polyline(op, index_pos, protected_layers, result)
    elif op.op_type == OpType.ADD_CIRCLE:
        _validate_add_circle(op, index_pos, protected_layers, result)
    elif op.op_type == OpType.ADD_ARC:
        _validate_add_arc(op, index_pos, protected_layers, result)
    elif op.op_type == OpType.ADD_TEXT:
        _validate_add_text(op, index_pos, protected_layers, result)


def _validate_add_block(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    rules: RuleConfig,
    result: ValidationResult,
) -> None:
    """Validate add_block parameters."""
    block_name = op.params.get("block_name")
    if not block_name:
        result.add_blocker("add_block requires block_name param", index_pos)
        return

    insert_point = op.params.get("insert_point")
    if not insert_point or "x" not in insert_point or "y" not in insert_point:
        result.add_blocker("add_block requires insert_point with x and y", index_pos)
        return

    if op.target_layer and op.target_layer.upper() in protected_layers:
        result.add_blocker(
            f"Cannot insert block on protected layer: {op.target_layer}",
            index_pos,
        )


def _validate_add_line(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Validate add_line parameters."""
    start = op.params.get("start")
    end = op.params.get("end")

    if not start or "x" not in start or "y" not in start:
        result.add_blocker("add_line requires start point with x and y", index_pos)
        return

    if not end or "x" not in end or "y" not in end:
        result.add_blocker("add_line requires end point with x and y", index_pos)
        return

    _check_creation_layer(op, index_pos, protected_layers, result)


def _validate_add_polyline(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Validate add_polyline parameters."""
    points = op.params.get("points")
    if not points or not isinstance(points, list):
        result.add_blocker("add_polyline requires points list", index_pos)
        return

    if len(points) < 2:
        result.add_blocker("add_polyline requires at least 2 points", index_pos)
        return

    for i, pt in enumerate(points):
        if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
            result.add_blocker(f"Point {i} must have x and y", index_pos)
            return

    _check_creation_layer(op, index_pos, protected_layers, result)


def _validate_add_circle(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Validate add_circle parameters."""
    center = op.params.get("center")
    if not center or "x" not in center or "y" not in center:
        result.add_blocker("add_circle requires center with x and y", index_pos)
        return

    radius = op.params.get("radius")
    if radius is None:
        result.add_blocker("add_circle requires radius", index_pos)
        return

    if not isinstance(radius, (int, float)) or radius <= 0:
        result.add_blocker("radius must be a positive number", index_pos)
        return

    _check_creation_layer(op, index_pos, protected_layers, result)


def _validate_add_arc(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Validate add_arc parameters."""
    center = op.params.get("center")
    if not center or "x" not in center or "y" not in center:
        result.add_blocker("add_arc requires center with x and y", index_pos)
        return

    radius = op.params.get("radius")
    if radius is None:
        result.add_blocker("add_arc requires radius", index_pos)
        return

    if not isinstance(radius, (int, float)) or radius <= 0:
        result.add_blocker("radius must be a positive number", index_pos)
        return

    if op.params.get("start_angle") is None:
        result.add_blocker("add_arc requires start_angle", index_pos)
        return

    if op.params.get("end_angle") is None:
        result.add_blocker("add_arc requires end_angle", index_pos)
        return

    _check_creation_layer(op, index_pos, protected_layers, result)


def _validate_add_text(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Validate add_text parameters."""
    text = op.params.get("text")
    if text is None:
        result.add_blocker("add_text requires text param", index_pos)
        return

    if not isinstance(text, str):
        result.add_blocker("text must be a string", index_pos)
        return

    insert = op.params.get("insert")
    if not insert or "x" not in insert or "y" not in insert:
        result.add_blocker("add_text requires insert point with x and y", index_pos)
        return

    _check_creation_layer(op, index_pos, protected_layers, result)


def _check_creation_layer(
    op: EditOperation,
    index_pos: int,
    protected_layers: list[str],
    result: ValidationResult,
) -> None:
    """Check that a creation op doesn't target a protected layer."""
    layer = op.params.get("layer") or op.target_layer
    if layer and layer.upper() in protected_layers:
        result.add_blocker(
            f"Cannot create entity on protected layer: {layer}",
            index_pos,
        )
