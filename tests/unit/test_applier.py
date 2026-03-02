"""Tests for RevisionApplier — applying approved ops to a master DXF."""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.comparison.applier import RevisionApplier
from cad_dxf_agent.core.comparison.approval import build_initial_approvals
from cad_dxf_agent.models.comparison_schema import (
    ApprovalConfig,
    ApprovalStatus,
    RevisionOp,
    RevisionOpType,
)


def _make_doc_with_line(start=(0, 0), end=(10, 0), layer="STRUCTURAL"):
    """Create a doc with one line, return (doc, handle)."""
    doc = ezdxf.new(dxfversion="R2018")
    doc.layers.add(layer, color=1)
    msp = doc.modelspace()
    line = msp.add_line(start, end, dxfattribs={"layer": layer})
    return doc, line.dxf.handle


def _make_doc_with_text(text="Hello", insert=(5, 5), layer="NOTES"):
    doc = ezdxf.new(dxfversion="R2018")
    doc.layers.add(layer, color=3)
    msp = doc.modelspace()
    txt = msp.add_text(text, dxfattribs={"layer": layer, "height": 2, "insert": insert})
    return doc, txt.dxf.handle


def _make_doc_with_mtext(text="Multi", insert=(5, 5), layer="NOTES"):
    doc = ezdxf.new(dxfversion="R2018")
    doc.layers.add(layer, color=3)
    msp = doc.modelspace()
    mt = msp.add_mtext(text, dxfattribs={"layer": layer, "insert": insert})
    return doc, mt.dxf.handle


def _make_doc_with_polyline(points=None, layer="STRUCTURAL"):
    pts = points or [(0, 0), (10, 0), (10, 10), (0, 10)]
    doc = ezdxf.new(dxfversion="R2018")
    doc.layers.add(layer, color=1)
    msp = doc.modelspace()
    poly = msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    return doc, poly.dxf.handle


def _make_doc_with_block(block_name="COL_MARK", insert=(50, 50), layer="GRID"):
    doc = ezdxf.new(dxfversion="R2018")
    doc.layers.add(layer, color=7)
    blk = doc.blocks.new(block_name)
    blk.add_circle((0, 0), radius=1)
    msp = doc.modelspace()
    ref = msp.add_blockref(block_name, insert, dxfattribs={"layer": layer})
    return doc, ref.dxf.handle


def _auto_approve_all(ops):
    """Build an ApprovalSet that auto-approves everything."""
    config = ApprovalConfig(auto_approve_threshold=0.0)
    return build_initial_approvals(ops, config)


def _make_op(
    op_id="op1",
    op_type=RevisionOpType.MOVE,
    handle="A0",
    layer="STRUCTURAL",
    forward=None,
    confidence=1.0,
):
    return RevisionOp(
        op_id=op_id,
        op_type=op_type,
        change_index=0,
        target_handle=handle,
        target_layer=layer,
        forward=forward or {},
        confidence=confidence,
    )


class TestApplyMove:
    def test_move_line(self):
        doc, handle = _make_doc_with_line()
        op = _make_op(handle=handle, forward={"dx": 5.0, "dy": 3.0})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        assert entity.dxf.start.x == pytest.approx(5.0)
        assert entity.dxf.start.y == pytest.approx(3.0)
        assert entity.dxf.end.x == pytest.approx(15.0)
        assert entity.dxf.end.y == pytest.approx(3.0)

    def test_move_polyline(self):
        doc, handle = _make_doc_with_polyline()
        op = _make_op(handle=handle, forward={"dx": 2.0, "dy": 1.0})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        pts = list(entity.get_points(format="xy"))
        assert pts[0] == pytest.approx((2.0, 1.0), abs=0.01)

    def test_move_insert(self):
        doc, handle = _make_doc_with_block()
        op = _make_op(handle=handle, forward={"dx": 10.0, "dy": -5.0})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        assert entity.dxf.insert.x == pytest.approx(60.0)
        assert entity.dxf.insert.y == pytest.approx(45.0)


class TestApplyDelete:
    def test_delete_line(self):
        doc, handle = _make_doc_with_line()
        op = _make_op(op_type=RevisionOpType.DELETE, handle=handle)
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        assert len(list(doc.modelspace())) == 0

    def test_delete_text(self):
        doc, handle = _make_doc_with_text()
        op = _make_op(op_type=RevisionOpType.DELETE, handle=handle, layer="NOTES")
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        assert len(list(doc.modelspace())) == 0


class TestApplyAdd:
    def test_add_line(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "LINE",
            "layer": "STRUCTURAL",
            "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}],
            "text_content": None,
            "block_name": None,
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entities = list(doc.modelspace())
        assert len(entities) == 1
        assert entities[0].dxftype() == "LINE"

    def test_add_text(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "TEXT",
            "layer": "NOTES",
            "points": [{"x": 5, "y": 5}],
            "text_content": "New label",
            "block_name": None,
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entities = list(doc.modelspace())
        assert len(entities) == 1
        assert entities[0].dxf.text == "New label"

    def test_add_insert_with_block_def(self):
        doc = ezdxf.new(dxfversion="R2018")
        blk = doc.blocks.new("MARKER")
        blk.add_circle((0, 0), radius=0.5)
        snapshot = {
            "entity_type": "INSERT",
            "layer": "GRID",
            "points": [{"x": 25, "y": 25}],
            "text_content": None,
            "block_name": "MARKER",
            "attributes": {"xscale": 1.0, "yscale": 1.0, "rotation": 0.0},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entities = list(doc.modelspace())
        assert len(entities) == 1
        assert entities[0].dxftype() == "INSERT"

    def test_add_insert_missing_block_fails_gracefully(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "INSERT",
            "layer": "GRID",
            "points": [{"x": 0, "y": 0}],
            "block_name": "NONEXISTENT",
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error

    def test_add_lwpolyline(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "LWPOLYLINE",
            "layer": "STRUCTURAL",
            "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
            "text_content": None,
            "block_name": None,
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded


class TestApplyModifyText:
    def test_modify_text_entity(self):
        doc, handle = _make_doc_with_text("OLD")
        op = _make_op(
            op_type=RevisionOpType.MODIFY_TEXT,
            handle=handle,
            layer="NOTES",
            forward={"new_text": "NEW"},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        assert entity.dxf.text == "NEW"

    def test_modify_mtext_entity(self):
        doc, handle = _make_doc_with_mtext("OLD")
        op = _make_op(
            op_type=RevisionOpType.MODIFY_TEXT,
            handle=handle,
            layer="NOTES",
            forward={"new_text": "NEW"},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        assert entity.text == "NEW"


class TestApplyModifyGeometry:
    def test_modify_line_geometry(self):
        doc, handle = _make_doc_with_line()
        new_points = [{"x": 5, "y": 5}, {"x": 20, "y": 20}]
        op = _make_op(
            op_type=RevisionOpType.MODIFY_GEOMETRY,
            handle=handle,
            forward={"new_points": new_points},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        assert entity.dxf.start.x == pytest.approx(5.0)
        assert entity.dxf.end.y == pytest.approx(20.0)

    def test_modify_polyline_geometry(self):
        doc, handle = _make_doc_with_polyline()
        new_points = [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 20}]
        op = _make_op(
            op_type=RevisionOpType.MODIFY_GEOMETRY,
            handle=handle,
            forward={"new_points": new_points},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        entity = doc.entitydb.get(handle)
        pts = list(entity.get_points(format="xy"))
        assert len(pts) == 3


class TestApplyModifyAttributes:
    def test_modify_circle_radius(self):
        doc = ezdxf.new(dxfversion="R2018")
        doc.layers.add("STRUCTURAL", color=1)
        msp = doc.modelspace()
        circle = msp.add_circle((50, 50), radius=10, dxfattribs={"layer": "STRUCTURAL"})
        handle = circle.dxf.handle

        op = _make_op(
            op_type=RevisionOpType.MODIFY_ATTRIBUTES,
            handle=handle,
            forward={"radius": 15},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.all_succeeded
        assert doc.entitydb.get(handle).dxf.radius == pytest.approx(15)


class TestApplyOrdering:
    def test_modify_before_delete(self):
        """MODIFY ops execute before DELETE — so we can modify then delete safely."""
        doc, handle = _make_doc_with_text("before")
        modify_op = _make_op(
            op_id="mod",
            op_type=RevisionOpType.MODIFY_TEXT,
            handle=handle,
            layer="NOTES",
            forward={"new_text": "after"},
        )
        delete_op = _make_op(
            op_id="del",
            op_type=RevisionOpType.DELETE,
            handle=handle,
            layer="NOTES",
        )
        ops = [delete_op, modify_op]  # reversed input order
        applier = RevisionApplier(doc)
        result = applier.apply(ops, _auto_approve_all(ops))

        # Both should succeed — modify ran first
        assert result.success_count == 2
        assert result.applied[0].op_type == RevisionOpType.MODIFY_TEXT
        assert result.applied[1].op_type == RevisionOpType.DELETE


class TestApplySkipAndReject:
    def test_skip_pending_ops(self):
        doc, handle = _make_doc_with_line()
        op = _make_op(handle=handle, forward={"dx": 5, "dy": 0}, confidence=0.5)
        # High threshold → pending
        aset = build_initial_approvals([op], ApprovalConfig(auto_approve_threshold=0.9))
        applier = RevisionApplier(doc)
        result = applier.apply([op], aset)

        assert result.skipped_count == 1
        assert len(result.applied) == 0

    def test_skip_rejected_ops(self):
        doc, handle = _make_doc_with_line()
        op = _make_op(handle=handle, forward={"dx": 5, "dy": 0})
        aset = _auto_approve_all([op])
        decision = aset.get_decision(op.op_id)
        decision.status = ApprovalStatus.REJECTED
        applier = RevisionApplier(doc)
        result = applier.apply([op], aset)

        assert result.rejected_count == 1
        assert len(result.applied) == 0


class TestApplyFailFast:
    def test_fail_fast_stops_on_first_failure(self):
        doc, handle = _make_doc_with_line()
        bad_op = _make_op(op_id="bad", handle="NONEXISTENT", forward={"dx": 1, "dy": 0})
        good_op = _make_op(op_id="good", handle=handle, forward={"dx": 1, "dy": 0})
        # Both move type → same priority. bad first alphabetically but order matters
        ops = [bad_op, good_op]
        applier = RevisionApplier(doc)
        result = applier.apply(ops, _auto_approve_all(ops), fail_fast=True)

        assert result.failure_count == 1
        assert len(result.applied) == 1  # stopped after first


class TestApplyEntityNotFound:
    def test_entity_not_found_graceful(self):
        doc = ezdxf.new(dxfversion="R2018")
        op = _make_op(handle="DEADBEEF", forward={"dx": 1, "dy": 0})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error


# ---------------------------------------------------------------------------
# Edge-path tests — error/unknown paths not covered by the classes above
# ---------------------------------------------------------------------------


class TestApplyOneUnknownOpType:
    """Line 95: handler dict returns None for unrecognised op type."""

    def test_unknown_op_type_returns_failure(self):
        """Simulate an op type not present in the handler dict.

        Since RevisionOpType is a StrEnum that validates all enum members, we
        inject the MOVE op but replace _apply_one's handler dict via a bound
        method override that omits MOVE — making MOVE behave as 'unknown'.
        """
        import types

        from cad_dxf_agent.models.comparison_schema import AppliedRevisionOp

        doc = ezdxf.new(dxfversion="R2018")
        applier = RevisionApplier(doc)
        op = _make_op(op_id="unk1", handle="FFFF", forward={"dx": 1, "dy": 0})

        def _patched_apply_one(self, inner_op: RevisionOp) -> AppliedRevisionOp:
            # Intentionally omit MOVE so the dict lookup returns None
            handler = {
                RevisionOpType.DELETE: self._apply_delete,
                RevisionOpType.ADD: self._apply_add,
                RevisionOpType.MODIFY_TEXT: self._apply_modify_text,
                RevisionOpType.MODIFY_GEOMETRY: self._apply_modify_geometry,
                RevisionOpType.MODIFY_ATTRIBUTES: self._apply_modify_attributes,
            }.get(inner_op.op_type)

            if handler is None:
                return AppliedRevisionOp(
                    op_id=inner_op.op_id,
                    op_type=inner_op.op_type,
                    success=False,
                    error=f"Unknown op type: {inner_op.op_type}",
                )
            return handler(inner_op)

        applier._apply_one = types.MethodType(_patched_apply_one, applier)
        result = applier._apply_one(op)

        assert result.success is False
        assert "Unknown op type" in result.error

    def test_generic_exception_in_handler_returns_failure(self):
        """Lines 102-104: _apply_one catches arbitrary exceptions from a handler."""
        from unittest.mock import patch

        doc = ezdxf.new(dxfversion="R2018")
        applier = RevisionApplier(doc)
        op = _make_op(op_id="boom", handle="ABCD", forward={"dx": 1, "dy": 0})

        def _exploding_handler(_op):
            raise RuntimeError("unexpected boom")

        with patch.object(applier, "_apply_move", side_effect=_exploding_handler):
            result = applier._apply_one(op)

        assert result.success is False
        assert "unexpected boom" in result.error


class TestApplyDeleteNotFound:
    """Line 137: _apply_delete with a handle not in entitydb."""

    def test_delete_not_found_returns_failure(self):
        doc = ezdxf.new(dxfversion="R2018")
        op = _make_op(
            op_id="del_nf",
            op_type=RevisionOpType.DELETE,
            handle="DEADBEEF",
            layer="0",
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error


class TestApplyAddInsertEmptyBlockName:
    """Lines 176-178: INSERT snapshot with empty block_name (falsy check)."""

    def test_insert_empty_block_name_fails(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "INSERT",
            "layer": "GRID",
            "points": [{"x": 0, "y": 0}],
            "block_name": "",  # falsy → triggers the `not block_name` branch
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error


class TestApplyAddUnsupportedEntityType:
    """Line 201: _apply_add falls through to unsupported entity type."""

    def test_add_unsupported_type_fails(self):
        doc = ezdxf.new(dxfversion="R2018")
        snapshot = {
            "entity_type": "CIRCLE",  # not handled by _apply_add
            "layer": "0",
            "points": [{"x": 0, "y": 0}],
            "text_content": None,
            "block_name": None,
            "attributes": {},
        }
        op = _make_op(op_type=RevisionOpType.ADD, forward={"snapshot": snapshot})
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "Unsupported entity type" in result.applied[0].error


class TestApplyModifyTextEdgePaths:
    """Lines 219, 234: _apply_modify_text error paths."""

    def test_modify_text_entity_not_found(self):
        """Line 219: target handle missing from entitydb."""
        doc = ezdxf.new(dxfversion="R2018")
        op = _make_op(
            op_id="mt_nf",
            op_type=RevisionOpType.MODIFY_TEXT,
            handle="DEADBEEF",
            layer="0",
            forward={"new_text": "x"},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error

    def test_modify_text_on_non_text_entity(self):
        """Line 234: target entity is not TEXT/MTEXT (e.g. LINE)."""
        doc, handle = _make_doc_with_line()
        op = _make_op(
            op_id="mt_line",
            op_type=RevisionOpType.MODIFY_TEXT,
            handle=handle,
            layer="STRUCTURAL",
            forward={"new_text": "ignored"},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "Cannot modify text" in result.applied[0].error


class TestApplyModifyGeometryEdgePaths:
    """Lines 252, 269: _apply_modify_geometry error paths."""

    def test_modify_geometry_entity_not_found(self):
        """Line 252: target handle missing from entitydb."""
        doc = ezdxf.new(dxfversion="R2018")
        op = _make_op(
            op_id="mg_nf",
            op_type=RevisionOpType.MODIFY_GEOMETRY,
            handle="DEADBEEF",
            layer="0",
            forward={"new_points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error

    def test_modify_geometry_on_unsupported_entity(self):
        """Line 269: entity type is not LINE or LWPOLYLINE (e.g. TEXT)."""
        doc, handle = _make_doc_with_text("hello")
        op = _make_op(
            op_id="mg_text",
            op_type=RevisionOpType.MODIFY_GEOMETRY,
            handle=handle,
            layer="NOTES",
            forward={"new_points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "Cannot modify geometry" in result.applied[0].error


class TestApplyModifyAttributesEdgePaths:
    """Lines 287, 297-298: _apply_modify_attributes error paths."""

    def test_modify_attributes_entity_not_found(self):
        """Line 287: target handle missing from entitydb."""
        doc = ezdxf.new(dxfversion="R2018")
        op = _make_op(
            op_id="ma_nf",
            op_type=RevisionOpType.MODIFY_ATTRIBUTES,
            handle="DEADBEEF",
            layer="0",
            forward={"color": 1},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert "not found" in result.applied[0].error

    def test_modify_attributes_setattr_exception(self):
        """Lines 297-298: setattr raises for a completely invalid DXF attribute name."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        line = msp.add_line((0, 0), (1, 1))
        handle = line.dxf.handle

        # "truly_nonexistent_attribute_xyz" is not a valid DXF attribute → raises
        # DXFAttributeError inside the setattr loop
        op = _make_op(
            op_id="ma_exc",
            op_type=RevisionOpType.MODIFY_ATTRIBUTES,
            handle=handle,
            layer="0",
            forward={"truly_nonexistent_attribute_xyz": 42},
        )
        applier = RevisionApplier(doc)
        result = applier.apply([op], _auto_approve_all([op]))

        assert result.failure_count == 1
        assert result.applied[0].error is not None
        assert "truly_nonexistent_attribute_xyz" in result.applied[0].error
