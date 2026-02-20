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
        index = EntityIndex(context)
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
    # Check op type is V1 supported
    if op.op_type not in OpType:
        result.add_blocker(f"Unsupported operation type: {op.op_type}", index_pos)
        return

    # For add_block, no target entity needed
    if op.op_type == OpType.ADD_BLOCK:
        _validate_add_block(op, index_pos, protected_layers, rules, result)
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
