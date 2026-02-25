"""GUI plan/apply tests — load fixture DXF, run plan via PipelineWorker."""

from __future__ import annotations

import pytest


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
