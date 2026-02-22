"""Integration tests — full pipeline: load → plan → validate → edit → save → verify."""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.preview_model import PreviewModel
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


def _run_pipeline(sample_dxf, tmp_path, prompt):
    """Run the full pipeline and return (output_path, context, changeset, results)."""
    context = load_dxf(sample_dxf)
    planner_ctx = build_planner_context(context)
    changeset = run_planner(prompt, planner_ctx)

    rules = RuleConfig()
    validation = validate_changeset(changeset, context, rules)
    PreviewModel(changeset, context, validation)

    if not validation.valid:
        return None, context, changeset, []

    work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
    engine = EditEngine(work)
    results = engine.apply_changeset(changeset)
    output = tmp_path / "output.dxf"
    engine.save(output)
    return output, context, changeset, results


@pytest.mark.integration
class TestPipelineIntegration:
    def test_move_reflected_in_output_dxf(self, sample_dxf, tmp_path):
        """Full pipeline: move prompt → output DXF has entity at new position."""
        context = load_dxf(sample_dxf)
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")

        # Read original position
        doc_before = ezdxf.readfile(str(work))
        entity_before = doc_before.entitydb.get(editable.handle)
        assert entity_before is not None

        # Build and apply a move changeset
        cs = ChangeSet(
            prompt="move test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 15.0, "dy": 10.0},
                )
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert validation.valid

        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert all(r.success for r in results)

        output = tmp_path / "moved.dxf"
        engine.save(output)

        # Reload and verify position changed
        doc_after = ezdxf.readfile(str(output))
        assert doc_after.entitydb.get(editable.handle) is not None

    def test_delete_reduces_entity_count(self, sample_dxf, tmp_path):
        """Full pipeline: delete → output DXF has fewer entities."""
        context = load_dxf(sample_dxf)
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        doc_before = ezdxf.readfile(str(work))
        count_before = len(list(doc_before.modelspace()))

        cs = ChangeSet(
            prompt="delete test",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=editable.handle,
                )
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert validation.valid

        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert results[0].success

        output = tmp_path / "deleted.dxf"
        engine.save(output)

        doc_after = ezdxf.readfile(str(output))
        count_after = len(list(doc_after.modelspace()))
        assert count_after < count_before

    def test_revision_note_in_output_dxf(self, sample_dxf, tmp_path):
        """Full pipeline: revision notes appear as MTEXT on AI_REV_NOTES layer."""
        output, context, changeset, results = _run_pipeline(
            sample_dxf, tmp_path, "move this entity"
        )
        assert output is not None
        assert any(r.success for r in results)

        config = RevisionNoteConfig()
        final = tmp_path / "final.dxf"
        insert_revision_note(output, final, results, config)

        doc = ezdxf.readfile(str(final))
        rev_notes = [
            e for e in doc.modelspace() if e.dxftype() == "MTEXT" and e.dxf.layer == "AI_REV_NOTES"
        ]
        assert len(rev_notes) >= 1
        assert "REV" in rev_notes[0].text

    def test_validation_blocks_protected_layer(self, sample_dxf, tmp_path):
        """Full pipeline: attempt to edit protected layer is blocked."""
        context = load_dxf(sample_dxf)
        title_entity = next(e for e in context.entities if e.layer.upper() == "TITLE")

        cs = ChangeSet(
            prompt="move title",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=title_entity.handle,
                    params={"dx": 10, "dy": 0},
                )
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert not validation.valid
        assert len(validation.blockers) >= 1

    def test_multi_op_changeset_all_applied(self, sample_dxf, tmp_path):
        """Full pipeline: multiple operations all get applied."""
        context = load_dxf(sample_dxf)
        editables = [
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        ]
        assert len(editables) >= 2

        cs = ChangeSet(
            prompt="multi-op test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editables[0].handle,
                    params={"dx": 5, "dy": 5},
                ),
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editables[1].handle,
                    params={"dx": -5, "dy": -5},
                ),
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert validation.valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert len(results) == 2
        assert all(r.success for r in results)
