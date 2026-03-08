"""Comprehensive tests for V2 transform operations: rotate, copy, scale, mirror.

Covers four test categories for each operation:
  - Validation (params, types, protected layers, edge cases)
  - Engine apply (success path, entity-not-found, geometric verification)
  - Preview model (description strings)
  - Revision notes (summary text)
  - Tool executor (operation queuing, error paths)
"""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.preview_model import PreviewModel
from cad_dxf_agent.core.revision_notes import generate_note_text
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.tool_executor import ToolExecutor
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.changes_schema import ValidationResult
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig
from cad_dxf_agent.models.ops_schema import AppliedChange, ChangeSet, EditOperation, OpType
from tests.helpers.changeset_factory import make_copy, make_mirror, make_rotate, make_scale

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_handle(context: DrawingContext, entity_type_str: str) -> str | None:
    """Return the first handle of the given entity type from a DrawingContext."""
    for e in context.entities:
        if e.entity_type.value == entity_type_str:
            return e.handle
    return None


def _get_editable_handle(context: DrawingContext, rule_config: RuleConfig) -> str:
    """Return the handle of the first entity on a non-protected layer."""
    protected_upper = {p.upper() for p in rule_config.protected_layers}
    for e in context.entities:
        if e.layer.upper() not in protected_upper:
            return e.handle
    pytest.fail("No editable entity found in context")


def _get_protected_handle(context: DrawingContext) -> str:
    """Return the handle of the first entity on the TITLE layer."""
    for e in context.entities:
        if e.layer.upper() == "TITLE":
            return e.handle
    pytest.fail("No TITLE-layer entity found in context")


def _copy_for_editing(source_path, tmp_path, name: str = "work.dxf"):
    """Copy sample DXF to a working path and return the path."""
    from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing

    return copy_dxf_for_editing(source_path, tmp_path / name)


def _get_first_handle_in_file(dxf_path, dxf_type: str) -> str | None:
    """Read a DXF file and return the handle of the first entity of the given type."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == dxf_type:
            return e.dxf.handle
    return None


def _get_line_start(dxf_path, handle: str) -> tuple[float, float]:
    """Return (x, y) of a LINE entity's start point."""
    doc = ezdxf.readfile(str(dxf_path))
    entity = doc.entitydb.get(handle)
    assert entity is not None and entity.dxftype() == "LINE"
    return entity.dxf.start.x, entity.dxf.start.y


# ---------------------------------------------------------------------------
# Minimal ToolExecutor fixture (mirrors test_tool_executor.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_context() -> DrawingContext:
    """Minimal DrawingContext with a LINE, TEXT, and a TITLE-protected TEXT."""
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="H1",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
                insert_point=Point2D(x=0, y=0),
            ),
            EntityRef(
                handle="H2",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=10, y=10),
                text_content="Label",
            ),
            EntityRef(
                handle="H3",
                entity_type=EntityType.TEXT,
                layer="TITLE",
                insert_point=Point2D(x=0, y=-20),
                text_content="PROJECT TITLE",
            ),
        ],
        layers=[
            LayerRule(name="STRUCTURAL", protected=False),
            LayerRule(name="NOTES", protected=False),
            LayerRule(name="TITLE", protected=True),
        ],
        blocks=[],
    )


@pytest.fixture
def executor(simple_context: DrawingContext) -> ToolExecutor:
    return ToolExecutor(
        simple_context, protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]
    )


# ===========================================================================
# ROTATE_ENTITY
# ===========================================================================


class TestRotateValidation:
    def test_valid_rotate_passes(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_rotate(handle, angle=90.0, cx=0, cy=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0

    def test_rotate_missing_angle_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle=handle,
                    params={},  # angle is required
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("angle" in b.message.lower() for b in result.blockers)

    def test_rotate_nan_angle_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle=handle,
                    params={"angle": float("nan")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any(
            "nan" in b.message.lower() or "inf" in b.message.lower() for b in result.blockers
        )

    def test_rotate_inf_angle_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle=handle,
                    params={"angle": float("inf")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_rotate_protected_layer_blocked(self, sample_context, rule_config):
        handle = _get_protected_handle(sample_context)
        cs = make_rotate(handle, angle=45.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_rotate_nonexistent_handle_blocked(self, sample_context, rule_config):
        cs = make_rotate("NONEXISTENT_HANDLE_XYZ", angle=90.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("not found" in b.message.lower() for b in result.blockers)

    def test_rotate_zero_angle_valid(self, sample_context, rule_config):
        """Zero-degree rotation is a no-op but still valid."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_rotate(handle, angle=0.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_rotate_full_circle_valid(self, sample_context, rule_config):
        """360-degree rotation is valid."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_rotate(handle, angle=360.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_rotate_negative_angle_valid(self, sample_context, rule_config):
        """Negative angles (clockwise) are permitted."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_rotate(handle, angle=-90.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestRotateEngine:
    def test_rotate_line_returns_success(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")
        assert handle is not None

        engine = EditEngine(work)
        cs = make_rotate(handle, angle=90.0, cx=0, cy=0)
        results = engine.apply_changeset(cs)

        assert results[0].success is True
        assert results[0].entity_handle == handle

    def test_rotate_description_contains_handle(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        cs = make_rotate(handle, angle=45.0)
        results = engine.apply_changeset(cs)

        assert handle in results[0].description

    def test_rotate_90deg_moves_line_start(self, sample_dxf, tmp_path):
        """Rotating a horizontal line 90° around origin should move start from (0,0) to (0,0)
        but the end should go from (100,0) to ~(0,100)."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")
        assert handle is not None

        # Record original end point
        doc_before = ezdxf.readfile(str(work))
        line_before = doc_before.entitydb.get(handle)
        end_x_before = line_before.dxf.end.x
        end_y_before = line_before.dxf.end.y

        engine = EditEngine(work)
        cs = make_rotate(handle, angle=90.0, cx=0, cy=0)
        engine.apply_changeset(cs)

        output = tmp_path / "rotated.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        line_after = doc_after.entitydb.get(handle)

        # After 90° CCW rotation around origin: (x,y) → (-y, x)
        expected_end_x = -end_y_before
        expected_end_y = end_x_before
        assert abs(line_after.dxf.end.x - expected_end_x) < 0.01
        assert abs(line_after.dxf.end.y - expected_end_y) < 0.01

    def test_rotate_around_nonzero_center(self, sample_dxf, tmp_path):
        """180° rotation around a non-origin center produces predictable coordinates."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        line_before = doc_before.entitydb.get(handle)
        start_x = line_before.dxf.start.x
        start_y = line_before.dxf.start.y

        # Rotate 180° around (50, 0): point (x,y) → (100-x, -y)
        engine = EditEngine(work)
        cs = make_rotate(handle, angle=180.0, cx=50, cy=0)
        engine.apply_changeset(cs)

        output = tmp_path / "rotated_center.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        line_after = doc_after.entitydb.get(handle)

        expected_x = 2 * 50 - start_x
        expected_y = 2 * 0 - start_y
        assert abs(line_after.dxf.start.x - expected_x) < 0.01
        assert abs(line_after.dxf.start.y - expected_y) < 0.01

    def test_rotate_entity_not_found_returns_failure(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        engine = EditEngine(work)
        cs = make_rotate("DOES_NOT_EXIST_999", angle=90.0)
        results = engine.apply_changeset(cs)

        assert results[0].success is False
        assert "not found" in results[0].description.lower()

    def test_rotate_multiple_entity_types(self, sample_dxf, tmp_path):
        """rotate_entity succeeds on LWPOLYLINE as well as LINE."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LWPOLYLINE")
        assert handle is not None, "Fixture must include an LWPOLYLINE"

        engine = EditEngine(work)
        cs = make_rotate(handle, angle=45.0, cx=25, cy=25)
        results = engine.apply_changeset(cs)
        assert results[0].success is True


class TestRotatePreview:
    def test_preview_description_contains_angle(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_rotate(handle, angle=90.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Rotate" in desc
        assert "90" in desc

    def test_preview_description_includes_entity_label(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_rotate(handle, angle=45.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        # Should include entity type and layer in brackets
        assert "LINE" in desc or "STRUCTURAL" in desc

    def test_preview_rotate_no_entity_found(self, sample_context):
        """Preview still renders a description even when the handle does not resolve."""
        cs = make_rotate("GHOST_HANDLE", angle=30.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Rotate" in desc
        assert "30" in desc


class TestRotateRevisionNotes:
    def test_rotate_note_contains_angle(self):
        config = RevisionNoteConfig(revision_number=2)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle="A1",
                    params={"angle": 90.0, "cx": 0, "cy": 0},
                ),
                success=True,
                entity_handle="A1",
                description="Rotated A1 by 90°",
            )
        ]
        note = generate_note_text(changes, config)

        assert note.startswith("REV 2")
        assert "90" in note
        assert "Rotated" in note

    def test_rotate_note_prefix_and_angle(self):
        config = RevisionNoteConfig(revision_number=7, prefix="REV")
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle="B2",
                    params={"angle": 45.0},
                ),
                success=True,
            )
        ]
        note = generate_note_text(changes, config)
        assert "REV 7" in note
        assert "45" in note

    def test_rotate_failed_change_excluded_from_note(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle="X1",
                    params={"angle": 90.0},
                ),
                success=False,
            )
        ]
        note = generate_note_text(changes, config)
        assert "No successful" in note


class TestRotateToolExecutor:
    def test_rotate_queues_operation(self, executor):
        result = executor.execute("rotate_entity", {"handle": "H1", "angle": 90.0})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ROTATE_ENTITY
        assert op.target_handle == "H1"
        assert op.params["angle"] == 90.0

    def test_rotate_includes_center_params(self, executor):
        executor.execute("rotate_entity", {"handle": "H1", "angle": 45.0, "cx": 10, "cy": 20})
        op = executor.operations[0]
        assert op.params["cx"] == 10
        assert op.params["cy"] == 20

    def test_rotate_defaults_cx_cy_to_zero(self, executor):
        executor.execute("rotate_entity", {"handle": "H1", "angle": 30.0})
        op = executor.operations[0]
        assert op.params["cx"] == 0
        assert op.params["cy"] == 0

    def test_rotate_protected_layer_returns_error(self, executor):
        result = executor.execute("rotate_entity", {"handle": "H3", "angle": 90.0})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_rotate_entity_not_found_returns_error(self, executor):
        result = executor.execute("rotate_entity", {"handle": "NONEXISTENT", "angle": 90.0})
        assert "error" in result
        assert len(executor.operations) == 0


# ===========================================================================
# COPY_ENTITY
# ===========================================================================


class TestCopyValidation:
    def test_valid_copy_passes(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_copy(handle, dx=30.0, dy=0.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0

    def test_copy_missing_dx_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle=handle,
                    params={"dy": 0.0},  # dx missing
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("dx" in b.message.lower() for b in result.blockers)

    def test_copy_missing_dy_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle=handle,
                    params={"dx": 10.0},  # dy missing
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_copy_nan_dx_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle=handle,
                    params={"dx": float("nan"), "dy": 0.0},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any(
            "nan" in b.message.lower() or "inf" in b.message.lower() for b in result.blockers
        )

    def test_copy_inf_dy_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle=handle,
                    params={"dx": 0.0, "dy": float("inf")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_copy_protected_layer_blocked(self, sample_context, rule_config):
        handle = _get_protected_handle(sample_context)
        cs = make_copy(handle, dx=10.0, dy=0.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_copy_nonexistent_handle_blocked(self, sample_context, rule_config):
        cs = make_copy("DOES_NOT_EXIST_ZZZ", dx=5.0, dy=5.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_copy_zero_offset_valid(self, sample_context, rule_config):
        """Copying with (0, 0) offset is valid (creates overlapping copy)."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_copy(handle, dx=0.0, dy=0.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestCopyEngine:
    def test_copy_returns_success(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")
        assert handle is not None

        engine = EditEngine(work)
        cs = make_copy(handle, dx=30.0, dy=0.0)
        results = engine.apply_changeset(cs)

        assert results[0].success is True

    def test_copy_returns_new_handle_different_from_original(self, sample_dxf, tmp_path):
        """The copy must get a fresh handle distinct from the original."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        cs = make_copy(handle, dx=10.0, dy=0.0)
        results = engine.apply_changeset(cs)

        assert results[0].success is True
        assert results[0].entity_handle != handle

    def test_copy_creates_additional_entity_in_dxf(self, sample_dxf, tmp_path):
        """Saving and reloading the DXF shows one more LINE than before."""
        work = _copy_for_editing(sample_dxf, tmp_path)

        doc_before = ezdxf.readfile(str(work))
        count_before = sum(1 for e in doc_before.modelspace() if e.dxftype() == "LINE")

        handle = _get_first_handle_in_file(work, "LINE")
        engine = EditEngine(work)
        cs = make_copy(handle, dx=50.0, dy=0.0)
        engine.apply_changeset(cs)

        output = tmp_path / "copied.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        count_after = sum(1 for e in doc_after.modelspace() if e.dxftype() == "LINE")

        assert count_after == count_before + 1

    def test_copy_places_new_entity_at_offset_position(self, sample_dxf, tmp_path):
        """The copied LINE's start point should be original + (dx, dy)."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        orig_start_x = doc_before.entitydb.get(handle).dxf.start.x
        orig_start_y = doc_before.entitydb.get(handle).dxf.start.y

        engine = EditEngine(work)
        cs = make_copy(handle, dx=25.0, dy=10.0)
        results = engine.apply_changeset(cs)
        new_handle = results[0].entity_handle

        output = tmp_path / "copy_offset.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        new_entity = doc_after.entitydb.get(new_handle)
        assert new_entity is not None

        assert abs(new_entity.dxf.start.x - (orig_start_x + 25.0)) < 0.01
        assert abs(new_entity.dxf.start.y - (orig_start_y + 10.0)) < 0.01

    def test_copy_does_not_modify_original_entity(self, sample_dxf, tmp_path):
        """The original entity's position should be unchanged after copy."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        orig_start_x = doc_before.entitydb.get(handle).dxf.start.x

        engine = EditEngine(work)
        cs = make_copy(handle, dx=50.0, dy=0.0)
        engine.apply_changeset(cs)

        output = tmp_path / "copy_orig.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        orig_entity = doc_after.entitydb.get(handle)

        assert abs(orig_entity.dxf.start.x - orig_start_x) < 0.01

    def test_copy_entity_not_found_returns_failure(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        engine = EditEngine(work)
        cs = make_copy("GHOST_HANDLE_999", dx=10.0, dy=0.0)
        results = engine.apply_changeset(cs)

        assert results[0].success is False
        assert "not found" in results[0].description.lower()

    def test_copy_lwpolyline_succeeds(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LWPOLYLINE")
        assert handle is not None

        engine = EditEngine(work)
        cs = make_copy(handle, dx=100.0, dy=0.0)
        results = engine.apply_changeset(cs)
        assert results[0].success is True


class TestCopyPreview:
    def test_preview_description_contains_copy_and_offset(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_copy(handle, dx=30.0, dy=15.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Copy" in desc
        assert "30" in desc
        assert "15" in desc

    def test_preview_copy_includes_entity_label(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_copy(handle, dx=10.0, dy=0.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "LINE" in desc or "STRUCTURAL" in desc

    def test_preview_copy_unknown_handle_still_renders(self, sample_context):
        cs = make_copy("UNKNOWN_HANDLE", dx=5.0, dy=5.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Copy" in desc


class TestCopyRevisionNotes:
    def test_copy_note_contains_offset(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle="A1",
                    params={"dx": 30.0, "dy": 0.0},
                ),
                success=True,
                entity_handle="NEW_HANDLE",
            )
        ]
        note = generate_note_text(changes, config)

        assert note.startswith("REV 1")
        assert "Copied" in note
        assert "30" in note

    def test_copy_note_shows_both_dx_dy(self):
        config = RevisionNoteConfig(revision_number=3)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle="B2",
                    params={"dx": 10.0, "dy": 20.0},
                ),
                success=True,
            )
        ]
        note = generate_note_text(changes, config)
        assert "10" in note
        assert "20" in note


class TestCopyToolExecutor:
    def test_copy_queues_operation(self, executor):
        result = executor.execute("copy_entity", {"handle": "H1", "dx": 30.0, "dy": 0.0})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.COPY_ENTITY
        assert op.target_handle == "H1"
        assert op.params["dx"] == 30.0
        assert op.params["dy"] == 0.0

    def test_copy_returns_handle_and_offset_in_result(self, executor):
        result = executor.execute("copy_entity", {"handle": "H1", "dx": 10.0, "dy": 5.0})
        assert result["handle"] == "H1"
        assert result["dx"] == 10.0
        assert result["dy"] == 5.0

    def test_copy_protected_layer_returns_error(self, executor):
        result = executor.execute("copy_entity", {"handle": "H3", "dx": 10.0, "dy": 0.0})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_copy_entity_not_found_returns_error(self, executor):
        result = executor.execute("copy_entity", {"handle": "GHOST", "dx": 5.0, "dy": 5.0})
        assert "error" in result
        assert len(executor.operations) == 0


# ===========================================================================
# SCALE_ENTITY
# ===========================================================================


class TestScaleValidation:
    def test_valid_scale_passes(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_scale(handle, factor=2.0, cx=0, cy=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0

    def test_scale_missing_factor_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={},  # factor missing
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("factor" in b.message.lower() for b in result.blockers)

    def test_scale_zero_factor_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={"factor": 0},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("zero" in b.message.lower() for b in result.blockers)

    def test_scale_negative_factor_warns(self, sample_context, rule_config):
        """Negative scale factor is allowed but generates a warning."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={"factor": -1.0},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid  # warning, not blocker
        assert len(result.warnings) == 1
        assert (
            "mirror" in result.warnings[0].message.lower()
            or "negative" in result.warnings[0].message.lower()
        )

    def test_scale_nan_factor_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={"factor": float("nan")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_scale_inf_factor_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={"factor": float("inf")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_scale_protected_layer_blocked(self, sample_context, rule_config):
        handle = _get_protected_handle(sample_context)
        cs = make_scale(handle, factor=2.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_scale_nonexistent_handle_blocked(self, sample_context, rule_config):
        cs = make_scale("NO_SUCH_ENTITY", factor=2.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_scale_factor_one_valid(self, sample_context, rule_config):
        """Factor of 1.0 is an identity scale — still valid."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_scale(handle, factor=1.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_scale_large_factor_valid(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_scale(handle, factor=1000.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestScaleEngine:
    def test_scale_returns_success(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        cs = make_scale(handle, factor=2.0, cx=0, cy=0)
        results = engine.apply_changeset(cs)

        assert results[0].success is True
        assert results[0].entity_handle == handle

    def test_scale_2x_doubles_line_length(self, sample_dxf, tmp_path):
        """Scaling a line by 2x from the origin doubles all coordinates."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        line_before = doc_before.entitydb.get(handle)
        end_x_before = line_before.dxf.end.x
        end_y_before = line_before.dxf.end.y

        engine = EditEngine(work)
        cs = make_scale(handle, factor=2.0, cx=0, cy=0)
        engine.apply_changeset(cs)

        output = tmp_path / "scaled2x.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        line_after = doc_after.entitydb.get(handle)

        assert abs(line_after.dxf.end.x - 2 * end_x_before) < 0.01
        assert abs(line_after.dxf.end.y - 2 * end_y_before) < 0.01

    def test_scale_around_nonzero_center(self, sample_dxf, tmp_path):
        """Scaling 2x around (50, 0): new_x = cx + factor*(old_x - cx)."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        line_before = doc_before.entitydb.get(handle)
        end_x_before = line_before.dxf.end.x

        engine = EditEngine(work)
        cs = make_scale(handle, factor=2.0, cx=50, cy=0)
        engine.apply_changeset(cs)

        output = tmp_path / "scaled_center.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        line_after = doc_after.entitydb.get(handle)

        expected_end_x = 50 + 2.0 * (end_x_before - 50)
        assert abs(line_after.dxf.end.x - expected_end_x) < 0.01

    def test_scale_half_shrinks_line(self, sample_dxf, tmp_path):
        """Scaling 0.5x from origin halves all coordinates."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        end_x_before = doc_before.entitydb.get(handle).dxf.end.x

        engine = EditEngine(work)
        cs = make_scale(handle, factor=0.5, cx=0, cy=0)
        engine.apply_changeset(cs)

        output = tmp_path / "scaled_half.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        end_x_after = doc_after.entitydb.get(handle).dxf.end.x

        assert abs(end_x_after - 0.5 * end_x_before) < 0.01

    def test_scale_entity_not_found_returns_failure(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        engine = EditEngine(work)
        cs = make_scale("MISSING_HANDLE_XYZ", factor=2.0)
        results = engine.apply_changeset(cs)

        assert results[0].success is False
        assert "not found" in results[0].description.lower()


class TestScalePreview:
    def test_preview_description_contains_factor(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_scale(handle, factor=3.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Scale" in desc
        assert "3.0" in desc

    def test_preview_scale_includes_entity_label(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_scale(handle, factor=2.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "LINE" in desc or "STRUCTURAL" in desc

    def test_preview_scale_description_shows_x_suffix(self, sample_context):
        """The description should include 'x' (e.g. '2.0x') for readability."""
        handle = _get_handle(sample_context, "LINE")
        cs = make_scale(handle, factor=2.0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "2.0x" in desc


class TestScaleRevisionNotes:
    def test_scale_note_contains_factor(self):
        config = RevisionNoteConfig(revision_number=4)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle="A1",
                    params={"factor": 2.5, "cx": 0, "cy": 0},
                ),
                success=True,
                entity_handle="A1",
            )
        ]
        note = generate_note_text(changes, config)

        assert note.startswith("REV 4")
        assert "Scaled" in note
        assert "2.5" in note

    def test_scale_note_includes_x_suffix(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle="C3",
                    params={"factor": 3.0},
                ),
                success=True,
            )
        ]
        note = generate_note_text(changes, config)
        assert "3.0x" in note

    def test_scale_failed_not_included_in_note(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle="Z9",
                    params={"factor": 2.0},
                ),
                success=False,
            )
        ]
        note = generate_note_text(changes, config)
        assert "No successful" in note


class TestScaleToolExecutor:
    def test_scale_queues_operation(self, executor):
        result = executor.execute("scale_entity", {"handle": "H1", "factor": 2.0})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.SCALE_ENTITY
        assert op.target_handle == "H1"
        assert op.params["factor"] == 2.0

    def test_scale_includes_center_params(self, executor):
        executor.execute("scale_entity", {"handle": "H1", "factor": 2.0, "cx": 50, "cy": 25})
        op = executor.operations[0]
        assert op.params["cx"] == 50
        assert op.params["cy"] == 25

    def test_scale_defaults_cx_cy_to_zero(self, executor):
        executor.execute("scale_entity", {"handle": "H1", "factor": 1.5})
        op = executor.operations[0]
        assert op.params["cx"] == 0
        assert op.params["cy"] == 0

    def test_scale_returns_factor_in_result(self, executor):
        result = executor.execute("scale_entity", {"handle": "H1", "factor": 4.0})
        assert result["factor"] == 4.0

    def test_scale_protected_layer_returns_error(self, executor):
        result = executor.execute("scale_entity", {"handle": "H3", "factor": 2.0})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_scale_entity_not_found_returns_error(self, executor):
        result = executor.execute("scale_entity", {"handle": "GHOST", "factor": 2.0})
        assert "error" in result
        assert len(executor.operations) == 0


# ===========================================================================
# MIRROR_ENTITY
# ===========================================================================


class TestMirrorValidation:
    def test_valid_mirror_x_axis_passes(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_mirror(handle, axis="x", value=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0

    def test_valid_mirror_y_axis_passes(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_mirror(handle, axis="y", value=50)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_mirror_missing_axis_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"value": 0},  # axis missing
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("axis" in b.message.lower() for b in result.blockers)

    def test_mirror_invalid_axis_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "z", "value": 0},  # only 'x' or 'y' allowed
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("axis" in b.message.lower() for b in result.blockers)

    def test_mirror_diagonal_axis_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "diagonal", "value": 0},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_mirror_nan_value_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "x", "value": float("nan")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any(
            "nan" in b.message.lower() or "inf" in b.message.lower() for b in result.blockers
        )

    def test_mirror_inf_value_blocked(self, sample_context, rule_config):
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "y", "value": float("inf")},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_mirror_protected_layer_blocked(self, sample_context, rule_config):
        handle = _get_protected_handle(sample_context)
        cs = make_mirror(handle, axis="x", value=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_mirror_nonexistent_handle_blocked(self, sample_context, rule_config):
        cs = make_mirror("NO_SUCH_ENTITY_XYZ", axis="x", value=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_mirror_value_optional_defaults_valid(self, sample_context, rule_config):
        """Omitting value (defaults to 0) is valid."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "x"},  # value omitted
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_mirror_negative_value_valid(self, sample_context, rule_config):
        """Negative axis value (e.g. mirror line at y=-10) is valid."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = make_mirror(handle, axis="x", value=-10.0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestMirrorEngine:
    def test_mirror_x_axis_returns_success(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        cs = make_mirror(handle, axis="x", value=0)
        results = engine.apply_changeset(cs)

        assert results[0].success is True
        assert results[0].entity_handle == handle

    def test_mirror_y_axis_returns_success(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        cs = make_mirror(handle, axis="y", value=50)
        results = engine.apply_changeset(cs)

        assert results[0].success is True

    def test_mirror_x_axis_flips_y_coordinate(self, sample_dxf, tmp_path):
        """Mirror across x-axis (y=0): new_y = -old_y for a line starting at y=0."""
        work = _copy_for_editing(sample_dxf, tmp_path)

        # Use the LWPOLYLINE which has points at y=0 and y=50 in conftest
        handle = _get_first_handle_in_file(work, "LWPOLYLINE")
        assert handle is not None

        doc_before = ezdxf.readfile(str(work))
        poly_before = doc_before.entitydb.get(handle)
        pts_before = list(poly_before.get_points())  # list of (x, y, ...) tuples
        # Get the point with highest y to verify flip
        max_y_before = max(pt[1] for pt in pts_before)

        engine = EditEngine(work)
        cs = make_mirror(handle, axis="x", value=0)
        engine.apply_changeset(cs)

        output = tmp_path / "mirror_x.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        poly_after = doc_after.entitydb.get(handle)
        pts_after = list(poly_after.get_points())
        min_y_after = min(pt[1] for pt in pts_after)

        # max_y_before should become -max_y_before (the minimum after flip)
        assert abs(min_y_after - (-max_y_before)) < 0.01

    def test_mirror_y_axis_flips_x_coordinate(self, sample_dxf, tmp_path):
        """Mirror across y-axis (x=0): new_x = -old_x."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        line_before = doc_before.entitydb.get(handle)
        end_x_before = line_before.dxf.end.x

        engine = EditEngine(work)
        cs = make_mirror(handle, axis="y", value=0)
        engine.apply_changeset(cs)

        output = tmp_path / "mirror_y.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        line_after = doc_after.entitydb.get(handle)

        # Mirror across y=0: new_x = -old_x
        assert abs(line_after.dxf.end.x - (-end_x_before)) < 0.01

    def test_mirror_x_axis_nonzero_value(self, sample_dxf, tmp_path):
        """Mirror across y=25: new_y = 2*25 - old_y."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        doc_before = ezdxf.readfile(str(work))
        start_y_before = doc_before.entitydb.get(handle).dxf.start.y

        engine = EditEngine(work)
        cs = make_mirror(handle, axis="x", value=25)
        engine.apply_changeset(cs)

        output = tmp_path / "mirror_x25.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        start_y_after = doc_after.entitydb.get(handle).dxf.start.y

        expected_y = 2 * 25 - start_y_before
        assert abs(start_y_after - expected_y) < 0.01

    def test_mirror_invalid_axis_in_engine_returns_failure(self, sample_dxf, tmp_path):
        """If axis='z' slips past validation, engine returns success=False."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)
        # Bypass the factory and set axis='z' directly
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "z", "value": 0},
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success is False
        assert (
            "invalid" in results[0].description.lower() or "axis" in results[0].description.lower()
        )

    def test_mirror_entity_not_found_returns_failure(self, sample_dxf, tmp_path):
        work = _copy_for_editing(sample_dxf, tmp_path)
        engine = EditEngine(work)
        cs = make_mirror("MISSING_ENTITY_ZZZ", axis="x", value=0)
        results = engine.apply_changeset(cs)

        assert results[0].success is False
        assert "not found" in results[0].description.lower()


class TestMirrorPreview:
    def test_preview_mirror_x_description(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_mirror(handle, axis="x", value=0)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Mirror" in desc
        assert "x=0" in desc

    def test_preview_mirror_y_description(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_mirror(handle, axis="y", value=50)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Mirror" in desc
        assert "y=50" in desc

    def test_preview_mirror_includes_entity_label(self, sample_context):
        handle = _get_handle(sample_context, "LINE")
        cs = make_mirror(handle, axis="x", value=10)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "LINE" in desc or "STRUCTURAL" in desc

    def test_preview_mirror_unknown_handle_still_renders(self, sample_context):
        cs = make_mirror("GHOST_HANDLE", axis="y", value=100)
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Mirror" in desc


class TestMirrorRevisionNotes:
    def test_mirror_note_contains_axis_and_value(self):
        config = RevisionNoteConfig(revision_number=5)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle="A1",
                    params={"axis": "x", "value": 0},
                ),
                success=True,
                entity_handle="A1",
            )
        ]
        note = generate_note_text(changes, config)

        assert note.startswith("REV 5")
        assert "Mirrored" in note
        assert "x=0" in note

    def test_mirror_note_y_axis(self):
        config = RevisionNoteConfig(revision_number=2)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle="B2",
                    params={"axis": "y", "value": 50},
                ),
                success=True,
            )
        ]
        note = generate_note_text(changes, config)
        assert "y=50" in note

    def test_mirror_failed_not_included_in_note(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle="X1",
                    params={"axis": "x", "value": 0},
                ),
                success=False,
            )
        ]
        note = generate_note_text(changes, config)
        assert "No successful" in note


class TestMirrorToolExecutor:
    def test_mirror_queues_operation(self, executor):
        result = executor.execute("mirror_entity", {"handle": "H1", "axis": "x"})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.MIRROR_ENTITY
        assert op.target_handle == "H1"
        assert op.params["axis"] == "x"

    def test_mirror_includes_value_param(self, executor):
        executor.execute("mirror_entity", {"handle": "H1", "axis": "y", "value": 50})
        op = executor.operations[0]
        assert op.params["value"] == 50

    def test_mirror_default_value_zero(self, executor):
        executor.execute("mirror_entity", {"handle": "H1", "axis": "x"})
        op = executor.operations[0]
        assert op.params["value"] == 0

    def test_mirror_returns_handle_and_axis_in_result(self, executor):
        result = executor.execute("mirror_entity", {"handle": "H1", "axis": "y"})
        assert result["handle"] == "H1"
        assert result["axis"] == "y"

    def test_mirror_protected_layer_returns_error(self, executor):
        result = executor.execute("mirror_entity", {"handle": "H3", "axis": "x"})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_mirror_entity_not_found_returns_error(self, executor):
        result = executor.execute("mirror_entity", {"handle": "GHOST", "axis": "x"})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_mirror_y_axis_queues_correctly(self, executor):
        result = executor.execute("mirror_entity", {"handle": "H2", "axis": "y", "value": 100})
        assert result["status"] == "queued"
        op = executor.operations[0]
        assert op.params["axis"] == "y"
        assert op.params["value"] == 100


# ===========================================================================
# Cross-operation integration tests
# ===========================================================================


class TestTransformCombinations:
    """Tests that combine multiple V2 transforms in a single changeset."""

    def test_rotate_then_copy_in_one_changeset(self, sample_context, rule_config):
        """A changeset with rotate + copy on different entities passes validation."""
        entities = [
            e
            for e in sample_context.entities
            if e.layer.upper() not in {p.upper() for p in rule_config.protected_layers}
        ]
        assert len(entities) >= 2, "Fixture must have at least 2 editable entities"

        cs = ChangeSet(
            prompt="rotate then copy",
            operations=[
                EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle=entities[0].handle,
                    params={"angle": 45.0, "cx": 0, "cy": 0},
                ),
                EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle=entities[1].handle,
                    params={"dx": 20.0, "dy": 0.0},
                ),
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_scale_and_mirror_same_entity_passes_validation(self, sample_context, rule_config):
        """Two ops on the same entity are both validated independently."""
        handle = _get_editable_handle(sample_context, rule_config)
        cs = ChangeSet(
            prompt="scale then mirror",
            operations=[
                EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle=handle,
                    params={"factor": 2.0, "cx": 0, "cy": 0},
                ),
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=handle,
                    params={"axis": "x", "value": 0},
                ),
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_mixed_valid_and_protected_in_one_changeset(self, sample_context, rule_config):
        """One valid op + one protected-layer op produces exactly one blocker."""
        valid_handle = _get_editable_handle(sample_context, rule_config)
        protected_handle = _get_protected_handle(sample_context)

        cs = ChangeSet(
            prompt="mixed",
            operations=[
                EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle=valid_handle,
                    params={"angle": 90.0},
                ),
                EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle=protected_handle,
                    params={"axis": "x", "value": 0},
                ),
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert len(result.blockers) == 1
        assert "protected layer" in result.blockers[0].message.lower()

    def test_all_four_transforms_in_sequence(self, sample_dxf, tmp_path):
        """Applying rotate → copy → scale → mirror in sequence all succeed."""
        work = _copy_for_editing(sample_dxf, tmp_path)
        handle = _get_first_handle_in_file(work, "LINE")

        engine = EditEngine(work)

        # Rotate the original
        results_rotate = engine.apply_changeset(make_rotate(handle, angle=30.0))
        assert results_rotate[0].success

        # Copy the (now rotated) line
        results_copy = engine.apply_changeset(make_copy(handle, dx=50.0, dy=0.0))
        assert results_copy[0].success
        copy_handle = results_copy[0].entity_handle

        # Scale the copy
        results_scale = engine.apply_changeset(make_scale(copy_handle, factor=0.5))
        assert results_scale[0].success

        # Mirror the copy
        results_mirror = engine.apply_changeset(make_mirror(copy_handle, axis="y", value=0))
        assert results_mirror[0].success

        output = tmp_path / "all_transforms.dxf"
        engine.save(output)
        # Verify the output is a valid DXF
        doc = ezdxf.readfile(str(output))
        assert doc is not None

    def test_tool_executor_accumulates_all_four_transform_ops(self, executor):
        """All four transform tools can accumulate in a single executor session."""
        executor.execute("rotate_entity", {"handle": "H1", "angle": 90.0})
        executor.execute("copy_entity", {"handle": "H1", "dx": 10.0, "dy": 0.0})
        executor.execute("scale_entity", {"handle": "H2", "factor": 2.0})
        executor.execute("mirror_entity", {"handle": "H2", "axis": "x"})

        assert len(executor.operations) == 4
        op_types = [op.op_type for op in executor.operations]
        assert OpType.ROTATE_ENTITY in op_types
        assert OpType.COPY_ENTITY in op_types
        assert OpType.SCALE_ENTITY in op_types
        assert OpType.MIRROR_ENTITY in op_types

    def test_revision_note_combines_all_four_transforms(self):
        """Multiple V2 transform changes join in a single note with semicolons."""
        config = RevisionNoteConfig(revision_number=9)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.ROTATE_ENTITY,
                    target_handle="A1",
                    params={"angle": 90.0},
                ),
                success=True,
            ),
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.COPY_ENTITY,
                    target_handle="B2",
                    params={"dx": 20.0, "dy": 0.0},
                ),
                success=True,
            ),
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.SCALE_ENTITY,
                    target_handle="C3",
                    params={"factor": 2.0},
                ),
                success=True,
            ),
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MIRROR_ENTITY,
                    target_handle="D4",
                    params={"axis": "x", "value": 0},
                ),
                success=True,
            ),
        ]
        note = generate_note_text(changes, config)
        assert note.startswith("REV 9")
        assert ";" in note  # Multiple summaries joined by semicolon
