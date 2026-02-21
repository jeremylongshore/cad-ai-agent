"""Tests for Pydantic schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.changes_schema import ValidationResult
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


class TestEntityRef:
    def test_create_line_entity(self):
        ref = EntityRef(
            handle="A1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            insert_point=Point2D(x=0, y=0),
        )
        assert ref.entity_type == EntityType.LINE
        assert ref.layer == "STRUCTURAL"
        assert ref.handle == "A1"

    def test_create_text_entity(self):
        ref = EntityRef(
            handle="B2",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            text_content="Column C-4",
        )
        assert ref.text_content == "Column C-4"

    def test_invalid_entity_type(self):
        with pytest.raises(ValidationError):
            EntityRef(
                handle="X",
                entity_type="VIEWPORT",  # Not a supported type
                layer="0",
            )


class TestEditOperation:
    def test_move_op(self):
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="A1",
            params={"dx": 10.0, "dy": 5.0},
        )
        assert op.op_type == OpType.MOVE_ENTITY
        assert op.params["dx"] == 10.0

    def test_invalid_op_type(self):
        with pytest.raises(ValidationError):
            EditOperation(op_type="scale_entity", target_handle="A1")


class TestChangeSet:
    def test_empty_changeset(self):
        cs = ChangeSet(prompt="test")
        assert cs.op_count == 0

    def test_changeset_with_ops(self):
        cs = ChangeSet(
            prompt="move column",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="A1",
                    params={"dx": 24, "dy": 0},
                )
            ],
        )
        assert cs.op_count == 1


class TestValidationResult:
    def test_initial_valid(self):
        result = ValidationResult()
        assert result.valid is True
        assert len(result.blockers) == 0

    def test_add_blocker_invalidates(self):
        result = ValidationResult()
        result.add_blocker("test error", 0)
        assert result.valid is False
        assert len(result.blockers) == 1

    def test_warning_does_not_invalidate(self):
        result = ValidationResult()
        result.add_warning("test warning")
        assert result.valid is True
        assert len(result.warnings) == 1


class TestRuleConfig:
    def test_defaults(self):
        config = RuleConfig()
        assert "TITLE" in config.protected_layers
        assert "TITLEBLOCK" in config.protected_layers
        assert "SEAL" in config.protected_layers
        assert "REVISION" in config.protected_layers

    def test_custom_protected(self):
        config = RuleConfig(protected_layers=["CUSTOM"])
        assert config.protected_layers == ["CUSTOM"]


class TestRevisionNoteConfig:
    def test_defaults(self):
        config = RevisionNoteConfig()
        assert config.enabled is True
        assert config.layer_name == "AI_REV_NOTES"
        assert config.prefix == "REV"
        assert config.revision_number == 1


class TestDrawingContext:
    def test_get_entity_by_handle(self):
        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(handle="A1", entity_type=EntityType.LINE, layer="0"),
                EntityRef(handle="B2", entity_type=EntityType.TEXT, layer="NOTES"),
            ],
        )
        found = ctx.get_entity_by_handle("B2")
        assert found is not None
        assert found.entity_type == EntityType.TEXT

    def test_missing_entity_returns_none(self):
        ctx = DrawingContext(file_path="test.dxf")
        assert ctx.get_entity_by_handle("MISSING") is None

    def test_protected_layers(self):
        ctx = DrawingContext(
            file_path="test.dxf",
            layers=[
                LayerRule(name="TITLE", protected=True),
                LayerRule(name="STRUCTURAL", protected=False),
            ],
        )
        assert ctx.get_protected_layers() == ["TITLE"]
