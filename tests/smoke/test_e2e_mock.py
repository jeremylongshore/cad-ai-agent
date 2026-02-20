"""End-to-end smoke test using mock planner — runs in pytest."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig


@pytest.mark.smoke
class TestE2EMockPipeline:
    """Full pipeline: load → plan → validate → apply → revision note → save."""

    def test_move_prompt(self, sample_dxf, tmp_path):
        output_dxf = tmp_path / "output.dxf"

        # Load
        context = load_dxf(sample_dxf)
        assert context.entity_count > 0

        # Plan
        drawing_ctx = build_planner_context(context)
        changeset = run_planner("Move the column east by 2 feet", drawing_ctx)
        assert changeset.op_count > 0

        # Validate
        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        assert validation.valid, f"Blockers: {[b.message for b in validation.blockers]}"

        # Apply
        engine = EditEngine(sample_dxf)
        results = engine.apply_changeset(changeset)
        engine.save(output_dxf)
        assert all(r.success for r in results)

        # Revision note
        rev_config = RevisionNoteConfig(revision_number=8)
        note = insert_revision_note(output_dxf, output_dxf, results, rev_config)
        assert note.startswith("REV 8")

        # Output file exists and is valid
        assert output_dxf.exists()
        verify_ctx = load_dxf(output_dxf)
        assert verify_ctx.entity_count > 0

    def test_delete_prompt(self, sample_dxf, tmp_path):
        output_dxf = tmp_path / "output_delete.dxf"

        context = load_dxf(sample_dxf)
        drawing_ctx = build_planner_context(context)
        changeset = run_planner("Delete the first element", drawing_ctx)
        assert changeset.op_count > 0

        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        assert validation.valid

        engine = EditEngine(sample_dxf)
        engine.apply_changeset(changeset)
        engine.save(output_dxf)
        assert output_dxf.exists()

    def test_text_edit_prompt(self, sample_dxf, tmp_path):
        output_dxf = tmp_path / "output_text.dxf"

        context = load_dxf(sample_dxf)
        drawing_ctx = build_planner_context(context)
        changeset = run_planner("Rename the text label", drawing_ctx)
        assert changeset.op_count > 0

        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        assert validation.valid

        engine = EditEngine(sample_dxf)
        engine.apply_changeset(changeset)
        engine.save(output_dxf)
        assert output_dxf.exists()

    def test_original_file_untouched(self, sample_dxf, tmp_path):
        """The original DXF must never be modified."""
        import hashlib

        original_hash = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()

        context = load_dxf(sample_dxf)
        drawing_ctx = build_planner_context(context)
        changeset = run_planner("Move something", drawing_ctx)

        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        if validation.valid:
            engine = EditEngine(sample_dxf)
            engine.apply_changeset(changeset)
            engine.save(tmp_path / "output.dxf")

        after_hash = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()
        assert original_hash == after_hash, "Original DXF was modified!"
