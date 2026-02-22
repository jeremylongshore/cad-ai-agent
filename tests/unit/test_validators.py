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

    def test_blocks_non_string_new_text(self, sample_context, rule_config):
        """edit_text with non-string new_text is blocked."""
        text_entity = next(
            e
            for e in sample_context.entities
            if e.text_content
            and e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]
        )
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_entity.handle,
                    params={"new_text": 42},
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "string" in result.blockers[0].message.lower()


class TestDeleteValidation:
    def test_delete_on_editable_layer_valid(self, sample_context, rule_config):
        """Delete on an editable layer passes validation."""
        editable = next(
            e
            for e in sample_context.entities
            if e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]
        )
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=editable.handle,
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert result.valid

    def test_delete_on_protected_layer_blocked(self, sample_context, rule_config):
        """Delete on a protected layer is blocked."""
        title_entity = next(e for e in sample_context.entities if e.layer.upper() == "TITLE")
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=title_entity.handle,
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "protected layer" in result.blockers[0].message.lower()


class TestAddBlockValidation:
    def test_add_block_missing_block_name(self, sample_context, rule_config):
        """add_block without block_name is blocked."""
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={"insert_point": {"x": 0, "y": 0}},
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "block_name" in result.blockers[0].message.lower()

    def test_add_block_missing_insert_point(self, sample_context, rule_config):
        """add_block without insert_point is blocked."""
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={"block_name": "COLUMN_MARK"},
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "insert_point" in result.blockers[0].message.lower()

    def test_add_block_on_protected_layer_blocked(self, sample_context, rule_config):
        """add_block targeting a protected layer is blocked."""
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    target_layer="TITLE",
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 0, "y": 0},
                    },
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "protected layer" in result.blockers[0].message.lower()

    def test_add_block_valid(self, sample_context, rule_config):
        """add_block with all required params on editable layer passes."""
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    target_layer="STRUCTURAL",
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 50, "y": 50},
                    },
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert result.valid


class TestMoveDistanceWarning:
    def test_max_move_distance_warning(self, sample_context):
        """Move beyond max_move_distance generates a warning (not blocker)."""
        from cad_dxf_agent.models.config_schema import RuleConfig

        rules = RuleConfig(max_move_distance=10.0)
        editable = next(
            e
            for e in sample_context.entities
            if e.layer.upper() not in [pl.upper() for pl in rules.protected_layers]
        )
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 100.0, "dy": 0.0},
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rules)
        # Should be valid (warning, not blocker)
        assert result.valid
        assert len(result.warnings) == 1
        assert "exceeds" in result.warnings[0].message.lower()

    def test_move_with_inf_blocked(self, sample_context, rule_config):
        """Move with Inf coordinate is blocked."""
        editable = next(
            e
            for e in sample_context.entities
            if e.layer.upper() not in [pl.upper() for pl in rule_config.protected_layers]
        )
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": float("inf"), "dy": 0},
                )
            ],
        )
        result = validate_changeset(changeset, sample_context, rule_config)
        assert not result.valid
        assert "inf" in result.blockers[0].message.lower()


class TestEmptyChangeset:
    def test_empty_changeset_valid(self, sample_context, rule_config):
        """An empty changeset passes validation."""
        changeset = ChangeSet(prompt="test", operations=[])
        result = validate_changeset(changeset, sample_context, rule_config)
        assert result.valid
        assert len(result.blockers) == 0
        assert len(result.warnings) == 0
