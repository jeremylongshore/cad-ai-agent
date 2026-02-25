"""GUI plan/apply tests — load fixture DXF, run plan via PipelineWorker."""

from __future__ import annotations

import ezdxf
import pytest


def _extract_dxf_summary(path: str) -> dict:
    """Extract entity counts, INSERT positions, and TEXT values from a DXF file."""
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    entities = list(msp)
    inserts = []
    texts = []
    for e in entities:
        if e.dxftype() == "INSERT":
            pos = e.dxf.insert
            inserts.append((round(pos.x, 2), round(pos.y, 2)))
        elif e.dxftype() in ("TEXT", "MTEXT"):
            t = e.dxf.text if e.dxftype() == "TEXT" else e.text
            texts.append(t)
    return {
        "count": len(entities),
        "inserts": inserts,
        "insert_count": len(inserts),
        "texts": texts,
        "text_count": len(texts),
    }


def _run_plan_apply(qapp, sample_dxf, rule_config, prompt, output_path):
    """Helper: plan + apply via PipelineWorker, return output path."""
    from cad_dxf_agent.core.dxf_reader import load_dxf
    from cad_dxf_agent.models.config_schema import RevisionNoteConfig
    from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

    context = load_dxf(sample_dxf)
    rev_config = RevisionNoteConfig(enabled=True, layer_name="AI_REV_NOTES")

    # Plan
    plan_worker = PipelineWorker()
    plan_worker.setup_plan(prompt, context, rule_config)
    plan_results, plan_errors = [], []
    plan_worker.plan_succeeded.connect(lambda r: plan_results.append(r))
    plan_worker.plan_failed.connect(lambda e: plan_errors.append(e))
    plan_worker.start()
    assert plan_worker.wait(10000), "Plan worker timed out"
    qapp.processEvents()
    assert len(plan_errors) == 0, f"Plan failed: {plan_errors}"
    assert len(plan_results) == 1

    # Apply
    apply_worker = PipelineWorker()
    apply_worker.setup_apply(
        plan_results[0].changeset, sample_dxf, output_path, rule_config, rev_config
    )
    apply_results, apply_errors = [], []
    apply_worker.apply_succeeded.connect(lambda r: apply_results.append(r))
    apply_worker.apply_failed.connect(lambda e: apply_errors.append(e))
    apply_worker.start()
    assert apply_worker.wait(10000), "Apply worker timed out"
    qapp.processEvents()
    assert len(apply_errors) == 0, f"Apply failed: {apply_errors}"
    assert len(apply_results) == 1
    return apply_results[0]


@pytest.mark.gui
class TestGuiPlanWorkflow:
    """Test plan workflow through PipelineWorker in headless mode."""

    def test_plan_via_worker(self, qapp, sample_dxf, rule_config):
        """Run plan pipeline via worker and verify result signals."""
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker, PlanResult

        context = load_dxf(sample_dxf)
        worker = PipelineWorker()
        worker.setup_plan("Move the column at grid C-4 two feet east", context, rule_config)

        results = []
        errors = []
        worker.plan_succeeded.connect(lambda r: results.append(r))
        worker.plan_failed.connect(lambda e: errors.append(e))
        worker.start()
        assert worker.wait(10000), "Worker timed out"
        qapp.processEvents()  # flush queued cross-thread signals

        assert len(errors) == 0, f"Plan failed: {errors}"
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, PlanResult)
        assert result.changeset.op_count > 0
        assert len(result.stages) == 4  # build_context, planner, validate, preview

    def test_apply_via_worker(self, qapp, sample_dxf, rule_config, tmp_path):
        """Run full plan+apply pipeline via workers."""
        from pathlib import Path

        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.models.config_schema import RevisionNoteConfig
        from cad_dxf_agent.ui.pipeline_worker import ApplyResult, PipelineWorker

        context = load_dxf(sample_dxf)
        output_path = str(tmp_path / "output.dxf")
        rev_config = RevisionNoteConfig(enabled=True, layer_name="AI_REV_NOTES")

        # Plan first
        plan_worker = PipelineWorker()
        plan_worker.setup_plan("Move the column at grid C-4 two feet east", context, rule_config)
        plan_results = []
        plan_worker.plan_succeeded.connect(lambda r: plan_results.append(r))
        plan_worker.start()
        assert plan_worker.wait(10000)
        qapp.processEvents()  # flush queued cross-thread signals
        assert len(plan_results) == 1

        changeset = plan_results[0].changeset

        # Apply
        apply_worker = PipelineWorker()
        apply_worker.setup_apply(changeset, sample_dxf, output_path, rule_config, rev_config)
        apply_results = []
        apply_errors = []
        apply_worker.apply_succeeded.connect(lambda r: apply_results.append(r))
        apply_worker.apply_failed.connect(lambda e: apply_errors.append(e))
        apply_worker.start()
        assert apply_worker.wait(10000)
        qapp.processEvents()  # flush queued cross-thread signals

        assert len(apply_errors) == 0, f"Apply failed: {apply_errors}"
        assert len(apply_results) == 1
        result = apply_results[0]
        assert isinstance(result, ApplyResult)
        assert result.output_path == output_path
        assert len(result.stages) >= 2  # edit_engine, save (+ optional revision_notes)

        # Verify output file exists
        assert Path(output_path).exists()


@pytest.mark.gui
class TestGuiSemanticValidation:
    """Verify PipelineWorker produces correct DXF output — same checks as E2E tests."""

    def test_move_changes_position(self, qapp, sample_dxf, rule_config, tmp_path):
        """Move preserves entity count but changes at least one INSERT position."""
        output_path = str(tmp_path / "move_output.dxf")
        _run_plan_apply(
            qapp, sample_dxf, rule_config,
            "Move the column at grid C-4 two feet east", output_path,
        )

        orig = _extract_dxf_summary(str(sample_dxf))
        edited = _extract_dxf_summary(output_path)

        # Move preserves entity and INSERT counts
        assert edited["count"] == orig["count"]
        assert edited["insert_count"] == orig["insert_count"]
        # At least one INSERT position must differ
        assert set(edited["inserts"]) != set(orig["inserts"]), \
            "Move should change at least one INSERT position"

    def test_delete_removes_entity(self, qapp, sample_dxf, rule_config, tmp_path):
        """Delete reduces total entity count."""
        output_path = str(tmp_path / "delete_output.dxf")
        _run_plan_apply(
            qapp, sample_dxf, rule_config,
            "Delete the first column mark", output_path,
        )

        orig = _extract_dxf_summary(str(sample_dxf))
        edited = _extract_dxf_summary(output_path)

        assert edited["count"] < orig["count"]
        fewer_inserts = edited["insert_count"] < orig["insert_count"]
        fewer_texts = edited["text_count"] < orig["text_count"]
        assert fewer_inserts or fewer_texts, \
            "Delete should remove at least one INSERT or TEXT"

    def test_edit_text_changes_content(self, qapp, sample_dxf, rule_config, tmp_path):
        """edit_text preserves entity count but changes text content."""
        output_path = str(tmp_path / "edittext_output.dxf")
        _run_plan_apply(
            qapp, sample_dxf, rule_config,
            "Rename the text label to UPDATED", output_path,
        )

        orig = _extract_dxf_summary(str(sample_dxf))
        edited = _extract_dxf_summary(output_path)

        # edit_text doesn't add or delete entities
        assert edited["count"] == orig["count"]
        # At least one TEXT value differs
        assert set(edited["texts"]) != set(orig["texts"]), \
            "edit_text should change at least one TEXT value"
        # The word "UPDATED" should appear somewhere
        assert any("UPDATED" in t.upper() for t in edited["texts"]), \
            'Edited text should contain "UPDATED"'
