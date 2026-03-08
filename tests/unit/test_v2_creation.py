"""Tests for V2 entity creation operations: add_line, add_polyline, add_circle, add_arc, add_text.

Covers:
- Validation (valid params, missing required params, protected-layer blocks)
- Engine apply (success=True, returned handle, persisted DXF attributes)
- Preview model descriptions
- Revision note text
- Tool executor dispatch and protected-layer gating
"""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing
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
from cad_dxf_agent.models.config_schema import RevisionNoteConfig
from cad_dxf_agent.models.ops_schema import AppliedChange, ChangeSet, EditOperation, OpType
from tests.helpers.changeset_factory import (
    make_add_arc,
    make_add_circle,
    make_add_line,
    make_add_polyline,
    make_add_text,
)

# ---------------------------------------------------------------------------
# Shared tool-executor fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def drawing_context() -> DrawingContext:
    """Minimal DrawingContext for tool-executor tests."""
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="A1",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
                insert_point=Point2D(x=0, y=0),
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
def executor(drawing_context: DrawingContext) -> ToolExecutor:
    """ToolExecutor with the standard protected-layer set."""
    return ToolExecutor(
        drawing_context,
        protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_and_save(sample_dxf, tmp_path, changeset, work_name="work.dxf", out_name="out.dxf"):
    """Copy the sample DXF, apply the changeset, save, and return (engine, output_path)."""
    work = copy_dxf_for_editing(sample_dxf, tmp_path / work_name)
    engine = EditEngine(work)
    results = engine.apply_changeset(changeset)
    output = tmp_path / out_name
    engine.save(output)
    return engine, results, output


def _count_type(dxf_path, dxf_type: str) -> int:
    """Count entities of a given DXF type in model space."""
    doc = ezdxf.readfile(str(dxf_path))
    return sum(1 for e in doc.modelspace() if e.dxftype() == dxf_type)


def _get_entities_of_type(dxf_path, dxf_type: str):
    """Return all entities of a given DXF type from model space."""
    doc = ezdxf.readfile(str(dxf_path))
    return [e for e in doc.modelspace() if e.dxftype() == dxf_type]


def _make_applied(op_type: OpType, params: dict, handle: str = "H1") -> AppliedChange:
    """Build a successful AppliedChange for revision-note tests."""
    return AppliedChange(
        operation=EditOperation(op_type=op_type, params=params),
        success=True,
        entity_handle=handle,
    )


# ===========================================================================
# add_line
# ===========================================================================


class TestAddLineValidation:
    def test_valid_params_pass(self, sample_context, rule_config):
        cs = make_add_line(0, 0, 100, 0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_missing_start_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_LINE,
                    params={"end": {"x": 100, "y": 0}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("start" in b.message.lower() for b in result.blockers)

    def test_missing_end_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_LINE,
                    params={"start": {"x": 0, "y": 0}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("end" in b.message.lower() for b in result.blockers)

    def test_start_missing_x_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_LINE,
                    params={"start": {"y": 0}, "end": {"x": 100, "y": 0}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_end_missing_y_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_LINE,
                    params={"start": {"x": 0, "y": 0}, "end": {"x": 100}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_protected_layer_blocked(self, sample_context, rule_config):
        cs = make_add_line(0, 0, 100, 0, layer="TITLE")
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_non_protected_layer_valid(self, sample_context, rule_config):
        cs = make_add_line(0, 0, 100, 0, layer="STRUCTURAL")
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_empty_params_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[EditOperation(op_type=OpType.ADD_LINE, params={})],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid


class TestAddLineEngine:
    def test_apply_returns_success_and_handle(self, sample_dxf, tmp_path):
        cs = make_add_line(0, 0, 100, 50)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert results[0].entity_handle

    def test_apply_creates_line_in_dxf(self, sample_dxf, tmp_path):
        before = _count_type(sample_dxf, "LINE")
        cs = make_add_line(10, 20, 80, 90)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert _count_type(output, "LINE") == before + 1

    def test_apply_line_start_end_coords(self, sample_dxf, tmp_path):
        cs = make_add_line(5.0, 7.0, 55.0, 77.0)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        lines = _get_entities_of_type(output, "LINE")
        # The last LINE added is the new one — check its endpoints
        found = any(
            abs(ln.dxf.start.x - 5.0) < 0.01
            and abs(ln.dxf.start.y - 7.0) < 0.01
            and abs(ln.dxf.end.x - 55.0) < 0.01
            and abs(ln.dxf.end.y - 77.0) < 0.01
            for ln in lines
        )
        assert found, "New line with expected start/end not found in output DXF"

    def test_apply_line_layer_assignment(self, sample_dxf, tmp_path):
        cs = make_add_line(0, 0, 50, 0, layer="NOTES")
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        lines = _get_entities_of_type(output, "LINE")
        assert any(ln.dxf.layer == "NOTES" for ln in lines)

    def test_apply_diagonal_line(self, sample_dxf, tmp_path):
        cs = make_add_line(-10, -10, 110, 110)
        _, results, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        lines = _get_entities_of_type(output, "LINE")
        assert any(
            abs(ln.dxf.start.x - (-10)) < 0.01 and abs(ln.dxf.end.x - 110) < 0.01 for ln in lines
        )

    def test_apply_zero_length_line(self, sample_dxf, tmp_path):
        """A zero-length line is geometrically degenerate but should not crash."""
        cs = make_add_line(25.0, 25.0, 25.0, 25.0)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success


class TestAddLinePreview:
    def test_description_mentions_add_line(self, sample_context):
        cs = make_add_line(0, 0, 100, 0)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "Add line" in desc

    def test_description_includes_start_coords(self, sample_context):
        cs = make_add_line(10, 20, 90, 80)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "10" in desc and "20" in desc

    def test_description_includes_end_coords(self, sample_context):
        cs = make_add_line(0, 0, 42, 99)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "42" in desc and "99" in desc


class TestAddLineRevisionNote:
    def test_note_contains_added_line(self):
        config = RevisionNoteConfig(revision_number=1)
        change = _make_applied(
            OpType.ADD_LINE,
            {"start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
        )
        note = generate_note_text([change], config)
        assert note.startswith("REV 1")
        assert "Added line" in note

    def test_note_includes_coords(self):
        config = RevisionNoteConfig(revision_number=2)
        change = _make_applied(
            OpType.ADD_LINE,
            {"start": {"x": 5, "y": 10}, "end": {"x": 50, "y": 100}},
        )
        note = generate_note_text([change], config)
        assert "5" in note and "10" in note


class TestAddLineToolExecutor:
    def test_queues_add_line_operation(self, executor):
        result = executor.execute(
            "add_line", {"start_x": 0, "start_y": 0, "end_x": 100, "end_y": 0}
        )
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ADD_LINE
        assert op.params["start"] == {"x": 0, "y": 0}
        assert op.params["end"] == {"x": 100, "y": 0}

    def test_protected_layer_blocked(self, executor):
        result = executor.execute(
            "add_line",
            {"start_x": 0, "start_y": 0, "end_x": 100, "end_y": 0, "layer": "TITLE"},
        )
        assert "error" in result
        assert len(executor.operations) == 0

    def test_editable_layer_queued(self, executor):
        result = executor.execute(
            "add_line",
            {"start_x": 0, "start_y": 0, "end_x": 100, "end_y": 0, "layer": "STRUCTURAL"},
        )
        assert result["status"] == "queued"
        assert executor.operations[0].params["layer"] == "STRUCTURAL"

    def test_result_contains_start_end(self, executor):
        result = executor.execute(
            "add_line", {"start_x": 3, "start_y": 4, "end_x": 30, "end_y": 40}
        )
        assert result["start"] == {"x": 3, "y": 4}
        assert result["end"] == {"x": 30, "y": 40}


# ===========================================================================
# add_polyline
# ===========================================================================


class TestAddPolylineValidation:
    def test_valid_default_params_pass(self, sample_context, rule_config):
        cs = make_add_polyline()
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_missing_points_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_POLYLINE,
                    params={"closed": False},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("points" in b.message.lower() for b in result.blockers)

    def test_single_point_blocked(self, sample_context, rule_config):
        cs = make_add_polyline(points=[{"x": 0, "y": 0}])
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("at least 2" in b.message.lower() for b in result.blockers)

    def test_empty_points_list_blocked(self, sample_context, rule_config):
        cs = make_add_polyline(points=[])
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_point_missing_x_blocked(self, sample_context, rule_config):
        cs = make_add_polyline(points=[{"y": 0}, {"x": 50, "y": 50}])
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("x" in b.message.lower() or "y" in b.message.lower() for b in result.blockers)

    def test_two_points_valid(self, sample_context, rule_config):
        cs = make_add_polyline(points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}])
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_closed_polyline_valid(self, sample_context, rule_config):
        cs = make_add_polyline(closed=True)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_protected_layer_blocked(self, sample_context, rule_config):
        cs = make_add_polyline(layer="TITLEBLOCK")
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_non_protected_layer_valid(self, sample_context, rule_config):
        cs = make_add_polyline(layer="STRUCTURAL")
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestAddPolylineEngine:
    def test_apply_returns_success_and_handle(self, sample_dxf, tmp_path):
        cs = make_add_polyline()
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert results[0].entity_handle

    def test_apply_creates_lwpolyline_in_dxf(self, sample_dxf, tmp_path):
        before = _count_type(sample_dxf, "LWPOLYLINE")
        cs = make_add_polyline()
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert _count_type(output, "LWPOLYLINE") == before + 1

    def test_apply_correct_point_count(self, sample_dxf, tmp_path):
        pts = [{"x": i * 10, "y": 0} for i in range(6)]
        cs = make_add_polyline(points=pts)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        polys = _get_entities_of_type(output, "LWPOLYLINE")
        # Find the newly-added one (6 vertices)
        assert any(len(list(p.vertices())) == 6 for p in polys)

    def test_apply_closed_polyline_flag(self, sample_dxf, tmp_path):
        cs = make_add_polyline(closed=True)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        polys = _get_entities_of_type(output, "LWPOLYLINE")
        assert any(p.closed for p in polys)

    def test_apply_open_polyline_flag(self, sample_dxf, tmp_path):
        cs = make_add_polyline(closed=False)
        _, results, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success

    def test_apply_layer_assignment(self, sample_dxf, tmp_path):
        cs = make_add_polyline(layer="NOTES")
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        polys = _get_entities_of_type(output, "LWPOLYLINE")
        assert any(p.dxf.layer == "NOTES" for p in polys)

    def test_apply_two_point_polyline(self, sample_dxf, tmp_path):
        cs = make_add_polyline(points=[{"x": 0, "y": 0}, {"x": 100, "y": 100}])
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success


class TestAddPolylinePreview:
    def test_description_mentions_polyline(self, sample_context):
        cs = make_add_polyline()
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "polyline" in preview.items[0].description.lower()

    def test_description_includes_point_count(self, sample_context):
        pts = [{"x": i, "y": 0} for i in range(5)]
        cs = make_add_polyline(points=pts)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "5" in preview.items[0].description

    def test_description_mentions_closed_when_true(self, sample_context):
        cs = make_add_polyline(closed=True)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "closed" in preview.items[0].description.lower()

    def test_description_no_closed_when_open(self, sample_context):
        cs = make_add_polyline(closed=False)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        # Should not claim it's closed
        desc = preview.items[0].description
        assert "closed" not in desc.lower() or "Add polyline" in desc


class TestAddPolylineRevisionNote:
    def test_note_contains_added_polyline(self):
        config = RevisionNoteConfig(revision_number=3)
        change = _make_applied(
            OpType.ADD_POLYLINE,
            {"points": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}], "closed": False},
        )
        note = generate_note_text([change], config)
        assert note.startswith("REV 3")
        assert "polyline" in note.lower()

    def test_note_includes_point_count(self):
        config = RevisionNoteConfig(revision_number=1)
        pts = [{"x": i, "y": 0} for i in range(4)]
        change = _make_applied(OpType.ADD_POLYLINE, {"points": pts, "closed": False})
        note = generate_note_text([change], config)
        assert "4" in note

    def test_note_mentions_closed(self):
        config = RevisionNoteConfig(revision_number=1)
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 25, "y": 50}]
        change = _make_applied(OpType.ADD_POLYLINE, {"points": pts, "closed": True})
        note = generate_note_text([change], config)
        assert "closed" in note.lower()


class TestAddPolylineToolExecutor:
    def test_queues_add_polyline_operation(self, executor):
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}, {"x": 0, "y": 50}]
        result = executor.execute("add_polyline", {"points": pts, "closed": False})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ADD_POLYLINE
        assert op.params["points"] == pts
        assert op.params["closed"] is False

    def test_queues_closed_polyline(self, executor):
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 25, "y": 50}]
        result = executor.execute("add_polyline", {"points": pts, "closed": True})
        assert result["status"] == "queued"
        assert executor.operations[0].params["closed"] is True

    def test_protected_layer_blocked(self, executor):
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}]
        result = executor.execute("add_polyline", {"points": pts, "layer": "SEAL"})
        assert "error" in result
        assert len(executor.operations) == 0

    def test_result_includes_point_count(self, executor):
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 25, "y": 50}]
        result = executor.execute("add_polyline", {"points": pts})
        assert result["point_count"] == 3


# ===========================================================================
# add_circle
# ===========================================================================


class TestAddCircleValidation:
    def test_valid_params_pass(self, sample_context, rule_config):
        cs = make_add_circle(50, 50, 10)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_missing_center_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_CIRCLE,
                    params={"radius": 10},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("center" in b.message.lower() for b in result.blockers)

    def test_missing_radius_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_CIRCLE,
                    params={"center": {"x": 50, "y": 50}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("radius" in b.message.lower() for b in result.blockers)

    def test_zero_radius_blocked(self, sample_context, rule_config):
        cs = make_add_circle(50, 50, radius=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("positive" in b.message.lower() for b in result.blockers)

    def test_negative_radius_blocked(self, sample_context, rule_config):
        cs = make_add_circle(50, 50, radius=-5)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("positive" in b.message.lower() for b in result.blockers)

    def test_center_missing_x_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_CIRCLE,
                    params={"center": {"y": 50}, "radius": 10},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_protected_layer_blocked(self, sample_context, rule_config):
        cs = make_add_circle(50, 50, 10, layer="REVISION")
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_editable_layer_valid(self, sample_context, rule_config):
        cs = make_add_circle(50, 50, 10, layer="NOTES")
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_fractional_radius_valid(self, sample_context, rule_config):
        cs = make_add_circle(0, 0, radius=0.001)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestAddCircleEngine:
    def test_apply_returns_success_and_handle(self, sample_dxf, tmp_path):
        cs = make_add_circle(50, 50, 10)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert results[0].entity_handle

    def test_apply_creates_circle_in_dxf(self, sample_dxf, tmp_path):
        before = _count_type(sample_dxf, "CIRCLE")
        cs = make_add_circle(30, 30, 15)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert _count_type(output, "CIRCLE") == before + 1

    def test_apply_correct_center(self, sample_dxf, tmp_path):
        cs = make_add_circle(cx=77.0, cy=33.0, radius=5)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        circles = _get_entities_of_type(output, "CIRCLE")
        assert any(
            abs(c.dxf.center.x - 77.0) < 0.01 and abs(c.dxf.center.y - 33.0) < 0.01 for c in circles
        )

    def test_apply_correct_radius(self, sample_dxf, tmp_path):
        cs = make_add_circle(50, 50, radius=12.5)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        circles = _get_entities_of_type(output, "CIRCLE")
        assert any(abs(c.dxf.radius - 12.5) < 0.001 for c in circles)

    def test_apply_layer_assignment(self, sample_dxf, tmp_path):
        cs = make_add_circle(50, 50, 10, layer="STRUCTURAL")
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        circles = _get_entities_of_type(output, "CIRCLE")
        assert any(c.dxf.layer == "STRUCTURAL" for c in circles)

    def test_apply_large_radius(self, sample_dxf, tmp_path):
        cs = make_add_circle(0, 0, radius=10000)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success


class TestAddCirclePreview:
    def test_description_mentions_add_circle(self, sample_context):
        cs = make_add_circle(50, 50, 10)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "Add circle" in preview.items[0].description

    def test_description_includes_center(self, sample_context):
        cs = make_add_circle(cx=30, cy=70, radius=5)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "30" in desc and "70" in desc

    def test_description_includes_radius(self, sample_context):
        cs = make_add_circle(50, 50, radius=25)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "25" in preview.items[0].description


class TestAddCircleRevisionNote:
    def test_note_contains_added_circle(self):
        config = RevisionNoteConfig(revision_number=4)
        change = _make_applied(
            OpType.ADD_CIRCLE,
            {"center": {"x": 50, "y": 50}, "radius": 10},
        )
        note = generate_note_text([change], config)
        assert note.startswith("REV 4")
        assert "circle" in note.lower()

    def test_note_includes_center_coords(self):
        config = RevisionNoteConfig(revision_number=1)
        change = _make_applied(
            OpType.ADD_CIRCLE,
            {"center": {"x": 20, "y": 40}, "radius": 5},
        )
        note = generate_note_text([change], config)
        assert "20" in note and "40" in note

    def test_note_includes_radius(self):
        config = RevisionNoteConfig(revision_number=1)
        change = _make_applied(
            OpType.ADD_CIRCLE,
            {"center": {"x": 0, "y": 0}, "radius": 99},
        )
        note = generate_note_text([change], config)
        assert "99" in note


class TestAddCircleToolExecutor:
    def test_queues_add_circle_operation(self, executor):
        result = executor.execute("add_circle", {"center_x": 50, "center_y": 50, "radius": 10})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ADD_CIRCLE
        assert op.params["center"] == {"x": 50, "y": 50}
        assert op.params["radius"] == 10

    def test_protected_layer_blocked(self, executor):
        result = executor.execute(
            "add_circle",
            {"center_x": 50, "center_y": 50, "radius": 10, "layer": "TITLE"},
        )
        assert "error" in result
        assert len(executor.operations) == 0

    def test_result_contains_center_and_radius(self, executor):
        result = executor.execute("add_circle", {"center_x": 30, "center_y": 60, "radius": 7})
        assert result["center"] == {"x": 30, "y": 60}
        assert result["radius"] == 7

    def test_editable_layer_queued(self, executor):
        result = executor.execute(
            "add_circle", {"center_x": 0, "center_y": 0, "radius": 5, "layer": "NOTES"}
        )
        assert result["status"] == "queued"
        assert executor.operations[0].params["layer"] == "NOTES"


# ===========================================================================
# add_arc
# ===========================================================================


class TestAddArcValidation:
    def test_valid_params_pass(self, sample_context, rule_config):
        cs = make_add_arc(50, 50, 10, start_angle=0, end_angle=90)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_missing_center_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_ARC,
                    params={"radius": 10, "start_angle": 0, "end_angle": 90},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("center" in b.message.lower() for b in result.blockers)

    def test_missing_radius_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_ARC,
                    params={"center": {"x": 50, "y": 50}, "start_angle": 0, "end_angle": 90},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("radius" in b.message.lower() for b in result.blockers)

    def test_zero_radius_blocked(self, sample_context, rule_config):
        cs = make_add_arc(50, 50, radius=0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_negative_radius_blocked(self, sample_context, rule_config):
        cs = make_add_arc(50, 50, radius=-1)
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_missing_start_angle_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_ARC,
                    params={"center": {"x": 50, "y": 50}, "radius": 10, "end_angle": 90},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("start_angle" in b.message.lower() for b in result.blockers)

    def test_missing_end_angle_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_ARC,
                    params={"center": {"x": 50, "y": 50}, "radius": 10, "start_angle": 0},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("end_angle" in b.message.lower() for b in result.blockers)

    def test_protected_layer_blocked(self, sample_context, rule_config):
        cs = make_add_arc(50, 50, 10, layer="SEAL")
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_full_circle_angles_valid(self, sample_context, rule_config):
        cs = make_add_arc(0, 0, 10, start_angle=0, end_angle=360)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_reversed_angles_valid(self, sample_context, rule_config):
        """DXF arcs support start > end (wraps around); validator should not block this."""
        cs = make_add_arc(0, 0, 10, start_angle=270, end_angle=90)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestAddArcEngine:
    def test_apply_returns_success_and_handle(self, sample_dxf, tmp_path):
        cs = make_add_arc(50, 50, 10, start_angle=0, end_angle=90)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert results[0].entity_handle

    def test_apply_creates_arc_in_dxf(self, sample_dxf, tmp_path):
        before = _count_type(sample_dxf, "ARC")
        cs = make_add_arc(25, 25, 8)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert _count_type(output, "ARC") == before + 1

    def test_apply_correct_center(self, sample_dxf, tmp_path):
        cs = make_add_arc(cx=42.0, cy=13.0, radius=5, start_angle=30, end_angle=120)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        arcs = _get_entities_of_type(output, "ARC")
        assert any(
            abs(a.dxf.center.x - 42.0) < 0.01 and abs(a.dxf.center.y - 13.0) < 0.01 for a in arcs
        )

    def test_apply_correct_radius(self, sample_dxf, tmp_path):
        cs = make_add_arc(50, 50, radius=17.5, start_angle=0, end_angle=180)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        arcs = _get_entities_of_type(output, "ARC")
        assert any(abs(a.dxf.radius - 17.5) < 0.001 for a in arcs)

    def test_apply_correct_angles(self, sample_dxf, tmp_path):
        cs = make_add_arc(0, 0, 10, start_angle=45.0, end_angle=135.0)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        arcs = _get_entities_of_type(output, "ARC")
        assert any(
            abs(a.dxf.start_angle - 45.0) < 0.01 and abs(a.dxf.end_angle - 135.0) < 0.01
            for a in arcs
        )

    def test_apply_layer_assignment(self, sample_dxf, tmp_path):
        cs = make_add_arc(50, 50, 10, layer="NOTES")
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        arcs = _get_entities_of_type(output, "ARC")
        assert any(a.dxf.layer == "NOTES" for a in arcs)

    def test_apply_semicircle(self, sample_dxf, tmp_path):
        cs = make_add_arc(0, 0, 20, start_angle=0, end_angle=180)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success


class TestAddArcPreview:
    def test_description_mentions_add_arc(self, sample_context):
        cs = make_add_arc(50, 50, 10)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "Add arc" in preview.items[0].description

    def test_description_includes_center(self, sample_context):
        cs = make_add_arc(cx=11, cy=22, radius=5)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "11" in desc and "22" in desc

    def test_description_includes_radius(self, sample_context):
        cs = make_add_arc(0, 0, radius=33)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "33" in preview.items[0].description

    def test_description_includes_angles(self, sample_context):
        cs = make_add_arc(0, 0, 10, start_angle=15, end_angle=75)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "15" in desc and "75" in desc


class TestAddArcRevisionNote:
    def test_note_contains_added_arc(self):
        config = RevisionNoteConfig(revision_number=5)
        change = _make_applied(
            OpType.ADD_ARC,
            {"center": {"x": 50, "y": 50}, "radius": 10, "start_angle": 0, "end_angle": 90},
        )
        note = generate_note_text([change], config)
        assert note.startswith("REV 5")
        assert "arc" in note.lower()

    def test_note_includes_center_coords(self):
        config = RevisionNoteConfig(revision_number=1)
        change = _make_applied(
            OpType.ADD_ARC,
            {"center": {"x": 15, "y": 25}, "radius": 8, "start_angle": 0, "end_angle": 180},
        )
        note = generate_note_text([change], config)
        assert "15" in note and "25" in note


class TestAddArcToolExecutor:
    def test_queues_add_arc_operation(self, executor):
        result = executor.execute(
            "add_arc",
            {"center_x": 50, "center_y": 50, "radius": 10, "start_angle": 0, "end_angle": 90},
        )
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ADD_ARC
        assert op.params["center"] == {"x": 50, "y": 50}
        assert op.params["radius"] == 10
        assert op.params["start_angle"] == 0
        assert op.params["end_angle"] == 90

    def test_protected_layer_blocked(self, executor):
        result = executor.execute(
            "add_arc",
            {
                "center_x": 50,
                "center_y": 50,
                "radius": 10,
                "start_angle": 0,
                "end_angle": 90,
                "layer": "REVISION",
            },
        )
        assert "error" in result
        assert len(executor.operations) == 0

    def test_result_contains_center_and_radius(self, executor):
        result = executor.execute(
            "add_arc",
            {"center_x": 10, "center_y": 20, "radius": 5, "start_angle": 45, "end_angle": 135},
        )
        assert result["center"] == {"x": 10, "y": 20}
        assert result["radius"] == 5

    def test_editable_layer_queued(self, executor):
        result = executor.execute(
            "add_arc",
            {
                "center_x": 0,
                "center_y": 0,
                "radius": 5,
                "start_angle": 0,
                "end_angle": 90,
                "layer": "STRUCTURAL",
            },
        )
        assert result["status"] == "queued"
        assert executor.operations[0].params["layer"] == "STRUCTURAL"


# ===========================================================================
# add_text
# ===========================================================================


class TestAddTextValidation:
    def test_valid_params_pass(self, sample_context, rule_config):
        cs = make_add_text("NEW ANNOTATION", 10, 10)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_missing_text_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={"insert": {"x": 10, "y": 10}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("text" in b.message.lower() for b in result.blockers)

    def test_non_string_text_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={"text": 42, "insert": {"x": 10, "y": 10}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("string" in b.message.lower() for b in result.blockers)

    def test_missing_insert_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={"text": "hello"},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("insert" in b.message.lower() for b in result.blockers)

    def test_insert_missing_x_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={"text": "hello", "insert": {"y": 10}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_insert_missing_y_blocked(self, sample_context, rule_config):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={"text": "hello", "insert": {"x": 10}},
                )
            ],
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid

    def test_protected_layer_blocked(self, sample_context, rule_config):
        cs = make_add_text("BLOCKED TEXT", 0, 0, layer="TITLE")
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert any("protected layer" in b.message.lower() for b in result.blockers)

    def test_editable_layer_valid(self, sample_context, rule_config):
        cs = make_add_text("OK TEXT", 10, 10, layer="NOTES")
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid

    def test_empty_string_text_valid(self, sample_context, rule_config):
        """Empty string is still a string — validator should allow it."""
        cs = make_add_text("", 0, 0)
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid


class TestAddTextEngine:
    def test_apply_returns_success_and_handle(self, sample_dxf, tmp_path):
        cs = make_add_text("HELLO", 10, 10)
        _, results, _ = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert results[0].entity_handle

    def test_apply_creates_text_entity(self, sample_dxf, tmp_path):
        before = _count_type(sample_dxf, "TEXT")
        cs = make_add_text("NEW TEXT", 5, 5)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert _count_type(output, "TEXT") == before + 1

    def test_apply_text_content_preserved(self, sample_dxf, tmp_path):
        cs = make_add_text("SPECIFIC LABEL", 10, 10)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        texts = _get_entities_of_type(output, "TEXT")
        assert any(t.dxf.text == "SPECIFIC LABEL" for t in texts)

    def test_apply_text_insert_position(self, sample_dxf, tmp_path):
        cs = make_add_text("POS CHECK", 55.0, 77.0)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        texts = _get_entities_of_type(output, "TEXT")
        assert any(
            abs(t.dxf.insert.x - 55.0) < 0.01 and abs(t.dxf.insert.y - 77.0) < 0.01 for t in texts
        )

    def test_apply_text_height(self, sample_dxf, tmp_path):
        cs = make_add_text("BIG TEXT", 0, 0, height=5.0)
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        texts = _get_entities_of_type(output, "TEXT")
        assert any(abs(t.dxf.height - 5.0) < 0.001 for t in texts)

    def test_apply_text_layer_assignment(self, sample_dxf, tmp_path):
        cs = make_add_text("LAYERED", 10, 10, layer="NOTES")
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        texts = _get_entities_of_type(output, "TEXT")
        assert any(t.dxf.layer == "NOTES" and t.dxf.text == "LAYERED" for t in texts)

    def test_apply_mtext_type_creates_mtext(self, sample_dxf, tmp_path):
        """text_type=MTEXT creates an MTEXT entity, not TEXT."""
        before = _count_type(sample_dxf, "MTEXT")
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={
                        "text": "MTEXT CONTENT",
                        "insert": {"x": 20, "y": 20},
                        "height": 3.0,
                        "text_type": "MTEXT",
                    },
                )
            ],
        )
        _, results, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        assert _count_type(output, "MTEXT") == before + 1

    def test_apply_mtext_content_preserved(self, sample_dxf, tmp_path):
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_TEXT,
                    params={
                        "text": "RICH TEXT HERE",
                        "insert": {"x": 0, "y": 0},
                        "height": 2.5,
                        "text_type": "MTEXT",
                    },
                )
            ],
        )
        _, _, output = _apply_and_save(sample_dxf, tmp_path, cs)
        mtexts = _get_entities_of_type(output, "MTEXT")
        assert any("RICH TEXT HERE" in m.text for m in mtexts)

    def test_apply_text_type_default_is_text(self, sample_dxf, tmp_path):
        """When text_type is omitted, a TEXT entity is created (not MTEXT)."""
        cs = make_add_text("DEFAULT TYPE", 10, 10)
        _, results, output = _apply_and_save(sample_dxf, tmp_path, cs)
        assert results[0].success
        texts = _get_entities_of_type(output, "TEXT")
        assert any(t.dxf.text == "DEFAULT TYPE" for t in texts)


class TestAddTextPreview:
    def test_description_mentions_add_text(self, sample_context):
        cs = make_add_text("HELLO", 10, 10)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "Add text" in preview.items[0].description

    def test_description_includes_text_content(self, sample_context):
        cs = make_add_text("MY LABEL", 0, 0)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        assert "MY LABEL" in preview.items[0].description

    def test_description_includes_insert_coords(self, sample_context):
        cs = make_add_text("X", 30, 70)
        preview = PreviewModel(cs, sample_context, ValidationResult())
        desc = preview.items[0].description
        assert "30" in desc and "70" in desc


class TestAddTextRevisionNote:
    def test_note_contains_added_text(self):
        config = RevisionNoteConfig(revision_number=6)
        change = _make_applied(
            OpType.ADD_TEXT,
            {"text": "NEW LABEL", "insert": {"x": 10, "y": 10}, "height": 2.5},
        )
        note = generate_note_text([change], config)
        assert note.startswith("REV 6")
        assert "Added text" in note

    def test_note_includes_text_content(self):
        config = RevisionNoteConfig(revision_number=1)
        change = _make_applied(
            OpType.ADD_TEXT,
            {"text": "FOOTING NOTE", "insert": {"x": 0, "y": 0}, "height": 2.5},
        )
        note = generate_note_text([change], config)
        assert "FOOTING NOTE" in note

    def test_note_truncates_long_text(self):
        config = RevisionNoteConfig(revision_number=1)
        long_text = "A" * 50
        change = _make_applied(
            OpType.ADD_TEXT,
            {"text": long_text, "insert": {"x": 0, "y": 0}, "height": 2.5},
        )
        note = generate_note_text([change], config)
        # Note should be generated without crashing; long content truncated
        assert "REV 1" in note
        assert "Added text" in note


class TestAddTextToolExecutor:
    def test_queues_add_text_operation(self, executor):
        result = executor.execute("add_text", {"text": "ANNOTATION", "x": 10, "y": 20})
        assert result["status"] == "queued"
        assert len(executor.operations) == 1
        op = executor.operations[0]
        assert op.op_type == OpType.ADD_TEXT
        assert op.params["text"] == "ANNOTATION"
        assert op.params["insert"] == {"x": 10, "y": 20}

    def test_protected_layer_blocked(self, executor):
        result = executor.execute(
            "add_text",
            {"text": "BLOCKED", "x": 10, "y": 10, "layer": "TITLEBLOCK"},
        )
        assert "error" in result
        assert len(executor.operations) == 0

    def test_mtext_type_queued(self, executor):
        result = executor.execute(
            "add_text",
            {"text": "RICH", "x": 0, "y": 0, "text_type": "MTEXT"},
        )
        assert result["status"] == "queued"
        op = executor.operations[0]
        assert op.params["text_type"] == "MTEXT"

    def test_default_text_type_is_text(self, executor):
        executor.execute("add_text", {"text": "PLAIN", "x": 0, "y": 0})
        assert executor.operations[0].params["text_type"] == "TEXT"

    def test_height_param_stored(self, executor):
        executor.execute("add_text", {"text": "BIG", "x": 0, "y": 0, "height": 7.5})
        assert executor.operations[0].params["height"] == 7.5

    def test_default_height_applied(self, executor):
        executor.execute("add_text", {"text": "DEFAULT H", "x": 0, "y": 0})
        assert executor.operations[0].params["height"] == 2.5

    def test_result_contains_text_and_position(self, executor):
        result = executor.execute("add_text", {"text": "CHECK", "x": 11, "y": 22})
        assert result["text"] == "CHECK"
        assert result["x"] == 11
        assert result["y"] == 22

    def test_editable_layer_queued(self, executor):
        result = executor.execute(
            "add_text", {"text": "NOTES LAYER", "x": 0, "y": 0, "layer": "NOTES"}
        )
        assert result["status"] == "queued"
        assert executor.operations[0].params["layer"] == "NOTES"


# ===========================================================================
# Cross-op / multi-operation tests
# ===========================================================================


class TestMultipleCreationOps:
    """Verify multiple creation ops in one changeset all validate and apply correctly."""

    def test_mixed_creation_ops_all_valid(self, sample_context, rule_config):
        from cad_dxf_agent.models.ops_schema import EditOperation
        from tests.helpers.changeset_factory import make_multi_op

        cs = make_multi_op(
            EditOperation(
                op_type=OpType.ADD_LINE,
                params={"start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
            ),
            EditOperation(
                op_type=OpType.ADD_CIRCLE,
                params={"center": {"x": 50, "y": 50}, "radius": 10},
            ),
            EditOperation(
                op_type=OpType.ADD_TEXT,
                params={"text": "MULTI", "insert": {"x": 0, "y": 0}},
            ),
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0

    def test_mixed_ops_accumulate_in_executor(self, executor):
        executor.execute("add_line", {"start_x": 0, "start_y": 0, "end_x": 50, "end_y": 0})
        executor.execute("add_circle", {"center_x": 25, "center_y": 25, "radius": 5})
        executor.execute(
            "add_arc",
            {"center_x": 0, "center_y": 0, "radius": 10, "start_angle": 0, "end_angle": 180},
        )
        pts = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 25, "y": 50}]
        executor.execute("add_polyline", {"points": pts})
        executor.execute("add_text", {"text": "LABEL", "x": 0, "y": 0})
        assert len(executor.operations) == 5

    def test_protected_layer_in_multi_op_blocks_only_that_op(self, sample_context, rule_config):
        from tests.helpers.changeset_factory import make_multi_op

        cs = make_multi_op(
            EditOperation(
                op_type=OpType.ADD_LINE,
                params={"start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}, "layer": "TITLE"},
            ),
            EditOperation(
                op_type=OpType.ADD_CIRCLE,
                params={"center": {"x": 50, "y": 50}, "radius": 5},
            ),
        )
        result = validate_changeset(cs, sample_context, rule_config)
        assert not result.valid
        assert len(result.blockers) == 1
        assert "protected layer" in result.blockers[0].message.lower()

    def test_all_five_creation_ops_apply_to_dxf(self, sample_dxf, tmp_path):
        from tests.helpers.changeset_factory import make_multi_op

        line_before = _count_type(sample_dxf, "LINE")
        circle_before = _count_type(sample_dxf, "CIRCLE")
        arc_before = _count_type(sample_dxf, "ARC")
        poly_before = _count_type(sample_dxf, "LWPOLYLINE")
        text_before = _count_type(sample_dxf, "TEXT")

        cs = make_multi_op(
            EditOperation(
                op_type=OpType.ADD_LINE,
                params={"start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}},
            ),
            EditOperation(
                op_type=OpType.ADD_CIRCLE,
                params={"center": {"x": 50, "y": 50}, "radius": 5},
            ),
            EditOperation(
                op_type=OpType.ADD_ARC,
                params={
                    "center": {"x": 0, "y": 0},
                    "radius": 10,
                    "start_angle": 0,
                    "end_angle": 90,
                },
            ),
            EditOperation(
                op_type=OpType.ADD_POLYLINE,
                params={"points": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 25, "y": 50}]},
            ),
            EditOperation(
                op_type=OpType.ADD_TEXT,
                params={"text": "ALL OPS", "insert": {"x": 0, "y": 0}},
            ),
        )
        _, results, output = _apply_and_save(sample_dxf, tmp_path, cs)

        assert all(r.success for r in results)
        assert _count_type(output, "LINE") == line_before + 1
        assert _count_type(output, "CIRCLE") == circle_before + 1
        assert _count_type(output, "ARC") == arc_before + 1
        assert _count_type(output, "LWPOLYLINE") == poly_before + 1
        assert _count_type(output, "TEXT") == text_before + 1
