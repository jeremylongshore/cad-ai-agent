"""Tests for preview_model — human-readable preview of proposed changes."""

from __future__ import annotations

from cad_dxf_agent.core.preview_model import PreviewItem, PreviewModel
from cad_dxf_agent.models.changes_schema import ValidationResult
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


class TestPreviewItem:
    def test_str_format(self):
        item = PreviewItem(0, "Move entity east")
        assert str(item) == "[0] Move entity east"

    def test_str_with_index(self):
        item = PreviewItem(3, "Delete column")
        assert str(item) == "[3] Delete column"


class TestPreviewModelDescriptions:
    def test_move_description(self, sample_context):
        """Move op produces a description with dx, dy."""
        editable = next(e for e in sample_context.entities if e.layer.upper() not in ("TITLE",))
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 24.0, "dy": 0.0},
                )
            ],
        )
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        assert len(preview.items) == 1
        desc = preview.items[0].description
        assert "Move" in desc
        assert "(24.0, 0.0)" in desc

    def test_edit_text_description(self, sample_context):
        """Edit text op includes the new text in the description."""
        text_entity = next(
            e for e in sample_context.entities if e.text_content and e.layer.upper() != "TITLE"
        )
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_entity.handle,
                    params={"new_text": "NEW LABEL"},
                )
            ],
        )
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Edit text" in desc
        assert "NEW LABEL" in desc

    def test_delete_description(self, sample_context):
        """Delete op mentions 'Delete' in the description."""
        editable = next(e for e in sample_context.entities if e.layer.upper() not in ("TITLE",))
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=editable.handle,
                )
            ],
        )
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "Delete" in desc

    def test_add_block_description(self, sample_context):
        """Add block op includes block name and insert point."""
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 50, "y": 50},
                    },
                )
            ],
        )
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)

        desc = preview.items[0].description
        assert "COLUMN_MARK" in desc
        assert "(50, 50)" in desc


class TestPreviewModelValidity:
    def test_is_valid_no_blockers(self, sample_context):
        """Preview reports valid when validation has no blockers."""
        cs = ChangeSet(prompt="test", operations=[])
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)
        assert preview.is_valid

    def test_is_valid_with_blockers(self, sample_context):
        """Preview reports invalid when validation has blockers."""
        cs = ChangeSet(prompt="test", operations=[])
        validation = ValidationResult()
        validation.add_blocker("Something is wrong", 0)
        preview = PreviewModel(cs, sample_context, validation)
        assert not preview.is_valid


class TestPreviewModelSummary:
    def test_summary_includes_operation_count(self, sample_context):
        editable = next(e for e in sample_context.entities if e.layer.upper() not in ("TITLE",))
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 1, "dy": 1},
                )
            ],
        )
        validation = ValidationResult()
        preview = PreviewModel(cs, sample_context, validation)
        assert "1 operation(s)" in preview.summary

    def test_summary_shows_blocked_when_invalid(self, sample_context):
        cs = ChangeSet(prompt="test", operations=[])
        validation = ValidationResult()
        validation.add_blocker("blocked!", 0)
        preview = PreviewModel(cs, sample_context, validation)
        assert "BLOCKED" in preview.summary
