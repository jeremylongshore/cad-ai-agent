"""Integration tests for PipelineWorker — signal sequence, cancellation, plan+apply."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    import PySide6  # noqa: F401

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

pytestmark = pytest.mark.skipif(not HAS_PYSIDE6, reason="PySide6 not installed")


@pytest.fixture(scope="module")
def qapp():
    """Provide a QApplication instance."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.integration
class TestPipelineWorkerPlan:
    """Test PipelineWorker plan mode."""

    def test_plan_emits_stage_signals(self, qapp, sample_dxf, rule_config):
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

        context = load_dxf(sample_dxf)
        worker = PipelineWorker()
        worker.setup_plan("Move column east", context, rule_config)

        started = []
        finished = []
        worker.stage_started.connect(lambda s: started.append(s))
        worker.stage_finished.connect(lambda s, d: finished.append((s, d)))
        worker.start()
        assert worker.wait(10000)

        assert len(started) == 4
        assert len(finished) == 4
        assert started[0] == "Build Context"
        assert started[1] == "Run Planner"
        assert started[2] == "Validate"
        assert started[3] == "Preview"

        # All durations should be non-negative
        for _name, dur in finished:
            assert dur >= 0

    def test_plan_result_has_stages(self, qapp, sample_dxf, rule_config):
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

        context = load_dxf(sample_dxf)
        worker = PipelineWorker()
        worker.setup_plan("Delete the line", context, rule_config)

        results = []
        worker.plan_succeeded.connect(lambda r: results.append(r))
        worker.start()
        assert worker.wait(10000)
        assert len(results) == 1

        plan = results[0]
        assert len(plan.stages) == 4
        assert all(s.success for s in plan.stages)
        assert all(s.duration_ms >= 0 for s in plan.stages)


@pytest.mark.integration
class TestPipelineWorkerApply:
    """Test PipelineWorker apply mode."""

    def test_apply_produces_output_file(self, qapp, sample_dxf, rule_config, tmp_path):
        from pathlib import Path

        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.models.config_schema import RevisionNoteConfig
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

        context = load_dxf(sample_dxf)
        output = str(tmp_path / "result.dxf")
        rev_config = RevisionNoteConfig(enabled=False)

        # Plan
        plan_w = PipelineWorker()
        plan_w.setup_plan("Move column east", context, rule_config)
        plan_results = []
        plan_w.plan_succeeded.connect(lambda r: plan_results.append(r))
        plan_w.start()
        assert plan_w.wait(10000)

        cs = plan_results[0].changeset

        # Apply
        apply_w = PipelineWorker()
        apply_w.setup_apply(cs, sample_dxf, output, rule_config, rev_config)
        apply_results = []
        apply_w.apply_succeeded.connect(lambda r: apply_results.append(r))
        apply_w.start()
        assert apply_w.wait(10000)

        assert len(apply_results) == 1
        assert Path(output).exists()
        assert apply_results[0].engine_doc is not None

    def test_apply_with_revision_notes(self, qapp, sample_dxf, rule_config, tmp_path):
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.models.config_schema import RevisionNoteConfig
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

        context = load_dxf(sample_dxf)
        output = str(tmp_path / "noted.dxf")
        rev_config = RevisionNoteConfig(enabled=True, layer_name="AI_REV_NOTES")

        # Plan
        plan_w = PipelineWorker()
        plan_w.setup_plan("Move column east", context, rule_config)
        plan_results = []
        plan_w.plan_succeeded.connect(lambda r: plan_results.append(r))
        plan_w.start()
        assert plan_w.wait(10000)

        cs = plan_results[0].changeset

        # Apply with notes
        apply_w = PipelineWorker()
        apply_w.setup_apply(cs, sample_dxf, output, rule_config, rev_config)
        apply_results = []
        apply_w.apply_succeeded.connect(lambda r: apply_results.append(r))
        apply_w.start()
        assert apply_w.wait(10000)

        assert len(apply_results) == 1
        # Should have 3 stages: edit_engine, save, revision_notes
        assert len(apply_results[0].stages) == 3
        assert apply_results[0].note_text != ""


@pytest.mark.integration
class TestPipelineWorkerCancellation:
    """Test cancellation between stages."""

    def test_cancel_before_start_is_noop(self, qapp, sample_dxf, rule_config):
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.ui.pipeline_worker import PipelineWorker

        context = load_dxf(sample_dxf)
        worker = PipelineWorker()
        worker.setup_plan("Move column", context, rule_config)
        worker.cancel()  # Should not raise

        # Start anyway — cancelled flag is reset in run()
        results = []
        worker.plan_succeeded.connect(lambda r: results.append(r))
        worker.start()
        assert worker.wait(10000)
        assert len(results) == 1  # Should succeed since cancel flag is reset
