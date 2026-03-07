"""Golden tests for the full preview + apply pipeline (EPIC-CAD-08).

End-to-end: build plan → validate → preview → apply → verify file.
Tests use real DXF files via the sample_dxf fixture.
"""

from __future__ import annotations

import ezdxf

from cad_dxf_agent.core.apply_pipeline import ApplyPipeline
from cad_dxf_agent.core.preview_builder import EditPreviewBuilder
from cad_dxf_agent.models.apply_schema import ApplyStatus, ApprovalDecision
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.plan_schema import EditAction, EditActionType, EditPlan
from cad_dxf_agent.models.preview_schema import PreviewStatus


def _find_entity(context, entity_type, layer=None, exclude_layer=None):
    """Find a specific entity in the context."""
    for e in context.entities:
        if e.entity_type == entity_type:
            if layer and e.layer != layer:
                continue
            if exclude_layer and e.layer == exclude_layer:
                continue
            return e
    return None


def test_golden_move(sample_dxf, sample_context, tmp_path):
    """Golden test: plan move → preview → approve → apply → verify position."""
    entity = _find_entity(sample_context, EntityType.LINE, layer="STRUCTURAL")
    assert entity is not None

    plan = EditPlan(
        requires_approval=True,
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                params={"dx": 10.0, "dy": 5.0},
            )
        ],
    )

    # Preview
    builder = EditPreviewBuilder(sample_context)
    preview = builder.build(plan)
    assert preview.status == PreviewStatus.READY
    assert len(preview.actions) == 1
    assert preview.actions[0].after_state.get("delta") == {"dx": 10.0, "dy": 5.0}

    # Apply with approval
    output = tmp_path / "golden_move.dxf"
    pipeline = ApplyPipeline(sample_context)
    approval = ApprovalDecision(plan_id=plan.plan_id, approved=True)
    result = pipeline.apply(plan, sample_dxf, output, approval=approval)

    assert result.status == ApplyStatus.SUCCESS
    assert result.success_count == 1
    assert output.exists()

    # Verify original unchanged
    original_size = sample_dxf.stat().st_size
    assert sample_dxf.stat().st_size == original_size


def test_golden_edit_text(sample_dxf, sample_context, tmp_path):
    """Golden test: plan text edit → preview → approve → apply → verify text."""
    entity = _find_entity(
        sample_context,
        EntityType.TEXT,
        exclude_layer="TITLE",
    )
    assert entity is not None

    plan = EditPlan(
        requires_approval=True,
        actions=[
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=entity.handle,
                target_layer=entity.layer,
                params={"new_text": "GOLDEN LABEL"},
            )
        ],
    )

    # Preview
    builder = EditPreviewBuilder(sample_context)
    preview = builder.build(plan)
    assert preview.status == PreviewStatus.READY
    assert preview.actions[0].before_state.get("text") == entity.text_content
    assert preview.actions[0].after_state.get("text") == "GOLDEN LABEL"

    # Apply
    output = tmp_path / "golden_text.dxf"
    pipeline = ApplyPipeline(sample_context)
    approval = ApprovalDecision(plan_id=plan.plan_id, approved=True)
    result = pipeline.apply(plan, sample_dxf, output, approval=approval)

    assert result.status == ApplyStatus.SUCCESS
    assert output.exists()

    # Verify text was actually changed in the DXF
    doc = ezdxf.readfile(str(output))
    ent = doc.entitydb.get(entity.handle)
    assert ent is not None
    assert ent.dxf.text == "GOLDEN LABEL"


def test_golden_delete(sample_dxf, sample_context, tmp_path):
    """Golden test: plan delete → preview → approve → apply → verify entity gone."""
    entity = _find_entity(
        sample_context,
        EntityType.TEXT,
        exclude_layer="TITLE",
    )
    assert entity is not None

    plan = EditPlan(
        requires_approval=True,
        actions=[
            EditAction(
                action_type=EditActionType.DELETE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
            )
        ],
    )

    # Preview
    builder = EditPreviewBuilder(sample_context)
    preview = builder.build(plan)
    assert preview.status == PreviewStatus.READY
    assert preview.actions[0].is_destructive is True
    assert preview.destructive_count == 1

    # Apply
    output = tmp_path / "golden_delete.dxf"
    pipeline = ApplyPipeline(sample_context)
    approval = ApprovalDecision(plan_id=plan.plan_id, approved=True)
    result = pipeline.apply(plan, sample_dxf, output, approval=approval)

    assert result.status == ApplyStatus.SUCCESS
    assert output.exists()

    # Verify entity was removed
    doc = ezdxf.readfile(str(output))
    assert doc.entitydb.get(entity.handle) is None


def test_golden_full_pipeline_with_revision_notes(sample_dxf, sample_context, tmp_path):
    """Golden test: full pipeline with revision notes enabled."""
    entity = _find_entity(
        sample_context,
        EntityType.TEXT,
        exclude_layer="TITLE",
    )
    assert entity is not None

    plan = EditPlan(
        requires_approval=False,
        actions=[
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=entity.handle,
                params={"new_text": "REVISED LABEL"},
            )
        ],
    )

    # Apply with revision notes
    from cad_dxf_agent.models.config_schema import RevisionNoteConfig

    output = tmp_path / "golden_notes.dxf"
    pipeline = ApplyPipeline(sample_context)
    rev_config = RevisionNoteConfig(enabled=True)
    result = pipeline.apply(plan, sample_dxf, output, revision_config=rev_config)

    assert result.status == ApplyStatus.SUCCESS
    assert result.revision_note is not None
    assert "REV 1" in result.revision_note
    assert output.exists()
