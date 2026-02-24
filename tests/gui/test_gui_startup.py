"""GUI startup tests — headless MainWindow instantiation."""

from __future__ import annotations

import pytest


@pytest.mark.gui
class TestMainWindowStartup:
    """Verify MainWindow can be created and has correct initial state."""

    def test_window_creates(self, qapp):
        from cad_dxf_agent.ui.main_window import MainWindow

        win = MainWindow()
        assert win.windowTitle() == "CAD DXF Agent — Structural Drawing Editor"

    def test_initial_button_states(self, qapp):
        from cad_dxf_agent.ui.main_window import MainWindow

        win = MainWindow()
        assert win.btn_plan.isEnabled() is False
        assert win.btn_apply.isEnabled() is False
        assert win.btn_undo.isEnabled() is False
        assert win.btn_redo.isEnabled() is False
        assert win.btn_timings.isEnabled() is False

    def test_progress_bar_hidden(self, qapp):
        from cad_dxf_agent.ui.main_window import MainWindow

        win = MainWindow()
        assert win.progress_bar.isHidden() is True
        assert win.lbl_stage.isHidden() is True

    def test_status_bar_labels(self, qapp):
        from cad_dxf_agent.ui.main_window import MainWindow

        win = MainWindow()
        assert "Entities: -" in win.lbl_entity_count.text()
        assert "Layers: -" in win.lbl_layer_count.text()

    def test_no_worker_on_init(self, qapp):
        from cad_dxf_agent.ui.main_window import MainWindow

        win = MainWindow()
        assert win._worker is None
