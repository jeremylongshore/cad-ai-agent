"""Tests for the validator engine."""

from __future__ import annotations

from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


class TestProtectedLayerBlocking:
    def test_blocks_edit_on_protected_layer(self, sample_context, rule_config):
        """Operations targeting entities on protected layers must be blocked."""
        # Find an entity on the TITLE layer
        title_entity = None
        for e in sample_context.entities:
            if e.layer.upper() == "TITLE":
                title_entity = e
                break
        assert title_entity is not None, "Fixture must have a TITLE layer entity"

        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=title_entity.handle,
                    params={"dx": 10, "dy": 0},
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert len(result.blockers) == 1
        assert "protected layer" in result.blockers[0].message.lower()

    def test_allows_edit_on_editable_layer(self, sample_context, rule_config):
        """Operations on non-protected layers should pass validation."""
        editable = None
        for e in sample_context.entities:
            if e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]:
                editable = e
                break
        assert editable is not None

        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 5, "dy": 5},
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert result.valid


class TestMoveValidation:
    def test_blocks_missing_dx_dy(self, sample_context, rule_config):
        editable = None
        for e in sample_context.entities:
            if e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]:
                editable = e
                break

        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={},  # Missing dx/dy
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid

    def test_blocks_nan_coordinates(self, sample_context, rule_config):
        editable = None
        for e in sample_context.entities:
            if e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]:
                editable = e
                break

        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": float("nan"), "dy": 0},
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid


class TestMissingEntity:
    def test_blocks_nonexistent_handle(self, sample_context, rule_config):
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="DOES_NOT_EXIST",
                    params={"dx": 1, "dy": 1},
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "not found" in result.blockers[0].message.lower()


class TestEditTextValidation:
    def test_blocks_missing_new_text(self, sample_context, rule_config):
        text_entity = None
        for e in sample_context.entities:
            if e.text_content and e.layer.upper() not in [
                pl.upper() for pl in rule_config.protected_layers
            ]:
                text_entity = e
                break
        assert text_entity is not None

        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_entity.handle,
                    params={},  # Missing new_text
                )
            ],
        )

        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
