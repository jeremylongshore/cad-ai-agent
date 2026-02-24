"""Main desktop window — PySide6 shell for the DXF editing workflow.

Full-featured desktop UI for Tony's structural drawing edits:
- File open (DXF/DWG/PDF with format detection)
- Layout/space selector
- Prompt input with history
- Per-operation approve/reject checkboxes
- Undo/redo (Ctrl+Z / Ctrl+Y)
- Export menu (DXF, PNG, PDF)
- Status bar with entity count and layer info
- Non-blocking pipeline with progress indicators
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.dxf_reader import load_dxf
from ..core.edit_history import EditHistory
from ..models.config_schema import RevisionNoteConfig, RuleConfig
from ..models.ops_schema import ChangeSet, EditOperation
from ..settings import settings
from .pipeline_worker import ApplyResult, PipelineWorker, PlanResult

logger = logging.getLogger(__name__)

FILE_FILTER = "CAD Files (*.dxf *.dwg *.pdf);;DXF Files (*.dxf);;All Files (*)"


class MainWindow(QMainWindow):
    """Primary application window for cad-dxf-agent."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAD DXF Agent — Structural Drawing Editor")
        self.setMinimumSize(1100, 700)

        self._dxf_path: Path | None = None
        self._context = None
        self._changeset: ChangeSet | None = None
        self._preview = None
        self._history: EditHistory | None = None
        self._op_checkboxes: list[QCheckBox] = []
        self._prompt_history: list[str] = []
        self._rule_config = RuleConfig(protected_layers=settings.protected_layers)
        self._rev_config = RevisionNoteConfig(
            enabled=settings.revision_notes_enabled,
            layer_name=settings.revision_notes_layer,
        )

        # Pipeline worker state
        self._worker: PipelineWorker | None = None
        self._last_stages: list = []
        self._plan_stage_count = 4  # build_context, planner, validate, preview
        self._apply_stage_count = 3  # edit_engine, save, revision_notes

        self._build_menu()
        self._build_toolbar()
        self._build_ui()
        self._build_statusbar()

    # ── Menu bar ──────────────────────────────────────────────────

    def _build_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_dxf = QAction("Export as &DXF...", self)
        export_dxf.triggered.connect(lambda: self._on_export("dxf"))
        file_menu.addAction(export_dxf)

        export_png = QAction("Export as &PNG...", self)
        export_png.triggered.connect(lambda: self._on_export("png"))
        file_menu.addAction(export_png)

        export_pdf = QAction("Export as P&DF...", self)
        export_pdf.triggered.connect(lambda: self._on_export("pdf"))
        file_menu.addAction(export_pdf)

        export_dwg = QAction("Export as D&WG...", self)
        export_dwg.triggered.connect(lambda: self._on_export("dwg"))
        file_menu.addAction(export_dwg)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.setEnabled(False)
        self._redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self._redo_action)

    # ── Toolbar ───────────────────────────────────────────────────

    def _build_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self._on_undo)
        toolbar.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self._on_redo)
        toolbar.addWidget(self.btn_redo)

        toolbar.addSeparator()

        self.btn_timings = QPushButton("Timings")
        self.btn_timings.setEnabled(False)
        self.btn_timings.clicked.connect(self._on_show_timings)
        toolbar.addWidget(self.btn_timings)

        self.btn_stats = QPushButton("Stats")
        self.btn_stats.setEnabled(False)
        self.btn_stats.clicked.connect(self._on_show_stats)
        toolbar.addWidget(self.btn_stats)

    # ── Main UI ───────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: file + prompt + controls ──
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)

        # File controls
        file_row = QHBoxLayout()
        self.btn_open = QPushButton("Open File...")
        self.btn_open.clicked.connect(self._on_open)
        file_row.addWidget(self.btn_open)

        self.lbl_file = QLabel("No file loaded")
        file_row.addWidget(self.lbl_file, 1)
        left.addLayout(file_row)

        # Load warnings (hidden by default)
        self.txt_warnings = QTextEdit()
        self.txt_warnings.setReadOnly(True)
        self.txt_warnings.setMaximumHeight(80)
        self.txt_warnings.hide()
        left.addWidget(self.txt_warnings)

        # Layout selector
        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Space:"))
        self.cmb_layout = QComboBox()
        self.cmb_layout.addItem("Model")
        self.cmb_layout.setEnabled(False)
        layout_row.addWidget(self.cmb_layout, 1)
        left.addLayout(layout_row)

        # Prompt input
        left.addWidget(QLabel("Edit prompt:"))
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setMaximumHeight(80)
        self.txt_prompt.setPlaceholderText('e.g. "Move the footing at grid C-4 two feet east"')
        left.addWidget(self.txt_prompt)

        # Action buttons
        btn_row = QHBoxLayout()
        self.btn_plan = QPushButton("Plan && Preview")
        self.btn_plan.setEnabled(False)
        self.btn_plan.clicked.connect(self._on_plan)
        btn_row.addWidget(self.btn_plan)

        self.btn_apply = QPushButton("Apply Selected")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)
        left.addLayout(btn_row)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        left.addWidget(self.progress_bar)

        self.lbl_stage = QLabel("")
        self.lbl_stage.hide()
        left.addWidget(self.lbl_stage)

        # Status log
        left.addWidget(QLabel("Log:"))
        self.txt_status = QTextEdit()
        self.txt_status.setReadOnly(True)
        self.txt_status.setMaximumHeight(150)
        left.addWidget(self.txt_status)

        left.addStretch()
        splitter.addWidget(left_widget)

        # ── Right panel: operations with checkboxes ──
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.addWidget(QLabel("Proposed Operations:"))

        # Select all / none
        select_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all_ops)
        select_row.addWidget(self.btn_select_all)
        self.btn_select_none = QPushButton("Select None")
        self.btn_select_none.clicked.connect(self._select_none_ops)
        select_row.addWidget(self.btn_select_none)
        select_row.addStretch()
        right.addLayout(select_row)

        # Scrollable operations area
        self.ops_scroll = QScrollArea()
        self.ops_scroll.setWidgetResizable(True)
        self.ops_container = QWidget()
        self.ops_layout = QVBoxLayout(self.ops_container)
        self.ops_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.ops_scroll.setWidget(self.ops_container)
        right.addWidget(self.ops_scroll)

        splitter.addWidget(right_widget)
        splitter.setSizes([450, 550])

        main_layout.addWidget(splitter)

    # ── Status bar ────────────────────────────────────────────────

    def _build_statusbar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        self.lbl_entity_count = QLabel("Entities: -")
        self.lbl_layer_count = QLabel("Layers: -")
        self.lbl_provider = QLabel(f"Provider: {settings.llm_provider}")
        status.addWidget(self.lbl_entity_count)
        status.addWidget(self.lbl_layer_count)
        status.addPermanentWidget(self.lbl_provider)

    # ── Helpers ───────────────────────────────────────────────────

    def _log_status(self, msg: str):
        self.txt_status.append(msg)
        logger.info(msg)

    def _update_undo_redo(self):
        can_undo = self._history is not None and self._history.can_undo
        can_redo = self._history is not None and self._history.can_redo
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)

    def _clear_ops(self):
        self._op_checkboxes.clear()
        while self.ops_layout.count():
            child = self.ops_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _select_all_ops(self):
        for cb in self._op_checkboxes:
            cb.setChecked(True)

    def _select_none_ops(self):
        for cb in self._op_checkboxes:
            cb.setChecked(False)

    def _show_load_warnings(self, warnings: list):
        """Display load warnings in the warnings panel."""
        if not warnings:
            self.txt_warnings.hide()
            return

        color_map = {"info": "#2196F3", "warning": "#FF9800", "error": "#F44336"}
        html_parts = []
        has_error = False
        for w in warnings:
            color = color_map.get(w.severity, "#666")
            label = w.severity.upper()
            html_parts.append(
                f'<span style="color:{color};font-weight:bold;">[{label}]</span> {w.message}'
            )
            if w.severity == "error":
                has_error = True

        self.txt_warnings.setHtml("<br>".join(html_parts))
        self.txt_warnings.show()

        # Error-level warnings disable the Plan button
        if has_error:
            self.btn_plan.setEnabled(False)

    # ── Event handlers ────────────────────────────────────────────

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open CAD File", "", FILE_FILTER)
        if not path:
            return

        try:
            file_path = Path(path)

            # DWG/PDF conversion if needed
            if file_path.suffix.lower() in (".dwg", ".pdf"):
                # Show PDF quality warning
                if file_path.suffix.lower() == ".pdf":
                    QMessageBox.warning(
                        self,
                        "PDF Conversion — Experimental",
                        "PDF conversion is experimental. Curves may be approximated "
                        "as line segments and some geometry may be lost.\n\n"
                        "For best results, export as DXF or DWG from your CAD software.",
                    )

                try:
                    from ..core.converter import convert_to_dxf

                    result = convert_to_dxf(file_path)
                    if result.success:
                        file_path = result.output_path
                        self._log_status(f"Converted {path} to DXF")
                        for w in result.warnings:
                            self._log_status(f"Warning: {w}")
                    else:
                        QMessageBox.warning(
                            self,
                            "Conversion",
                            f"Conversion issue: {result.error}\nTrying to load anyway.",
                        )
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Missing Converter",
                        "DWG/PDF conversion requires the convert extra.\n"
                        "Install with: pip install -e '.[convert]'",
                    )
                    return

            self._dxf_path = file_path
            self._context = load_dxf(self._dxf_path)
            self._history = EditHistory(self._dxf_path)

            # Update UI
            self.lbl_file.setText(f"{self._dxf_path.name} ({self._context.entity_count} entities)")
            self.btn_plan.setEnabled(True)
            self.btn_apply.setEnabled(False)
            self.btn_stats.setEnabled(True)
            self._changeset = None
            self._preview = None
            self._clear_ops()
            self._update_undo_redo()

            # Populate layout selector
            self.cmb_layout.clear()
            for layout in self._context.layouts:
                self.cmb_layout.addItem(f"{layout.name} ({layout.entity_count})")
            self.cmb_layout.setEnabled(len(self._context.layouts) > 1)

            # Update status bar with editable/total counts
            protected_upper = {p.upper() for p in settings.protected_layers}
            editable_count = sum(
                1 for e in self._context.entities if e.layer.upper() not in protected_upper
            )
            total_layers = len(self._context.layers)
            protected_count = sum(1 for lyr in self._context.layers if lyr.protected)
            self.lbl_entity_count.setText(
                f"Entities: {editable_count}/{self._context.entity_count}"
            )
            self.lbl_layer_count.setText(f"Layers: {total_layers - protected_count}/{total_layers}")

            # Display load warnings
            self._show_load_warnings(self._context.load_warnings)

            self._log_status(f"Loaded: {self._dxf_path.name}")
            if self._context.unsupported_entity_types:
                self._log_status(
                    f"Skipped types: {', '.join(self._context.unsupported_entity_types)}"
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
            logger.error("File load error: %s", traceback.format_exc())

    def _on_plan(self):
        if not self._context:
            return

        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "No Prompt", "Enter a prompt describing the edit.")
            return

        # Save to prompt history
        if prompt not in self._prompt_history:
            self._prompt_history.append(prompt)

        # Cancel any running worker
        self._cancel_worker()

        self._log_status(f"Planning: {prompt[:60]}...")
        self.btn_plan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self._show_progress(self._plan_stage_count)

        worker = PipelineWorker(self)
        worker.setup_plan(prompt, self._context, self._rule_config)
        worker.stage_started.connect(self._on_stage_started)
        worker.stage_finished.connect(self._on_stage_finished)
        worker.plan_succeeded.connect(self._on_plan_succeeded)
        worker.plan_failed.connect(self._on_plan_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_apply(self):
        if not self._changeset or not self._dxf_path:
            return

        # Build filtered changeset from checked operations only
        selected_ops: list[EditOperation] = []
        for i, cb in enumerate(self._op_checkboxes):
            if cb.isChecked() and i < len(self._changeset.operations):
                selected_ops.append(self._changeset.operations[i])

        if not selected_ops:
            QMessageBox.warning(self, "No Operations", "Select at least one operation to apply.")
            return

        # File dialog stays on main thread (native dialog)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As New DXF",
            str(self._dxf_path.with_stem(self._dxf_path.stem + "_edited")),
            "DXF Files (*.dxf)",
        )
        if not output_path:
            return

        # Cancel any running worker
        self._cancel_worker()

        filtered = ChangeSet(
            prompt=self._changeset.prompt,
            operations=selected_ops,
            revision_label=self._changeset.revision_label,
        )

        self.btn_plan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self._show_progress(self._apply_stage_count)

        worker = PipelineWorker(self)
        worker.setup_apply(
            filtered, self._dxf_path, output_path, self._rule_config, self._rev_config
        )
        worker.stage_started.connect(self._on_stage_started)
        worker.stage_finished.connect(self._on_stage_finished)
        worker.apply_succeeded.connect(self._on_apply_succeeded)
        worker.apply_failed.connect(self._on_apply_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    # ── Worker signal slots ──────────────────────────────────────

    def _on_stage_started(self, stage_name: str):
        self.lbl_stage.setText(f"Stage: {stage_name}...")
        self.statusBar().showMessage(f"Running: {stage_name}")

    def _on_stage_finished(self, stage_name: str, duration_ms: float):
        self._log_status(f"  {stage_name}: {duration_ms:.0f} ms")
        self.progress_bar.setValue(self.progress_bar.value() + 1)

    def _on_plan_succeeded(self, result: PlanResult):
        self._last_stages = result.stages
        self.btn_timings.setEnabled(True)
        self._changeset = result.changeset
        self._preview = result.preview

        # Build per-operation checkboxes
        self._clear_ops()
        for item in self._preview.items:
            cb = QCheckBox(str(item))
            cb.setChecked(True)
            self._op_checkboxes.append(cb)
            self.ops_layout.addWidget(cb)

        if not result.validation.valid:
            for b in result.validation.blockers:
                lbl = QLabel(f"BLOCKED: {b.message}")
                lbl.setStyleSheet("color: red; font-weight: bold;")
                self.ops_layout.addWidget(lbl)
            self._log_status(f"Plan blocked: {len(result.validation.blockers)} issue(s)")
            self.btn_apply.setEnabled(False)
        else:
            self._log_status(f"Plan valid: {self._changeset.op_count} operation(s)")
            self.btn_apply.setEnabled(True)

        for w in result.validation.warnings:
            self._log_status(f"Warning: {w.message}")

    def _on_plan_failed(self, error: str):
        QMessageBox.critical(self, "Planner Error", f"Planning failed:\n{error}")
        logger.error("Planner error: %s", error)
        self.btn_plan.setEnabled(self._context is not None)

    def _on_apply_succeeded(self, result: ApplyResult):
        self._last_stages = result.stages
        self.btn_timings.setEnabled(True)

        # Push to edit history for undo support
        if self._history:
            success_count = sum(1 for r in result.applied_changes if r.success)
            self._history.push(result.engine_doc, f"Applied {success_count} op(s)")
            self._update_undo_redo()

        success_count = sum(1 for r in result.applied_changes if r.success)
        total = len(result.applied_changes)
        self._log_status(f"Applied {success_count}/{total} operations")

        if result.note_text:
            self._log_status(f"Revision note: {result.note_text}")

        self._log_status(f"Saved to: {result.output_path}")
        QMessageBox.information(self, "Success", f"Saved to:\n{result.output_path}")

    def _on_apply_failed(self, error: str):
        QMessageBox.critical(self, "Apply Error", f"Apply/save failed:\n{error}")
        logger.error("Apply error: %s", error)

    def _on_worker_finished(self):
        self._hide_progress()
        self._worker = None
        self.btn_plan.setEnabled(self._context is not None)

    # ── Progress helpers ───────────────────────────────────────

    def _show_progress(self, stage_count: int):
        self.progress_bar.setMaximum(stage_count)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_stage.show()

    def _hide_progress(self):
        self.progress_bar.hide()
        self.lbl_stage.hide()
        self.lbl_stage.setText("")
        self.statusBar().clearMessage()

    def _cancel_worker(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
            self._worker = None

    # ── Timings dialog ─────────────────────────────────────────

    def _on_show_timings(self):
        if not self._last_stages:
            return

        lines = ["Stage Timings", "=" * 40]
        total_ms = 0.0
        for sr in self._last_stages:
            status = "OK" if sr.success else f"FAIL: {sr.error}"
            lines.append(f"  {sr.stage.value:20s}  {sr.duration_ms:8.1f} ms  {status}")
            total_ms += sr.duration_ms
        lines.append("-" * 40)
        lines.append(f"  {'Total':20s}  {total_ms:8.1f} ms")
        text = "\n".join(lines)

        dlg = QDialog(self)
        dlg.setWindowTitle("Pipeline Timings")
        dlg.setMinimumSize(450, 300)
        layout = QVBoxLayout(dlg)

        txt = QPlainTextEdit(text)
        txt.setReadOnly(True)
        layout.addWidget(txt)

        btn_box = QDialogButtonBox()
        btn_copy = btn_box.addButton("Copy to Clipboard", QDialogButtonBox.ButtonRole.ActionRole)
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        btn_close = btn_box.addButton(QDialogButtonBox.StandardButton.Close)
        btn_close.clicked.connect(dlg.close)
        layout.addWidget(btn_box)

        dlg.exec()

    # ── Stats dialog ─────────────────────────────────────────

    def _on_show_stats(self):
        if not self._context:
            return

        from ..core.context_builder import drawing_stats, support_report

        stats = drawing_stats(self._context, protected_layers=settings.protected_layers)
        report_text = support_report(stats)

        dlg = QDialog(self)
        dlg.setWindowTitle("Drawing Statistics")
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)

        txt = QPlainTextEdit(report_text)
        txt.setReadOnly(True)
        layout.addWidget(txt)

        btn_box = QDialogButtonBox()
        btn_copy = btn_box.addButton("Copy Report", QDialogButtonBox.ButtonRole.ActionRole)
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(report_text))
        btn_close = btn_box.addButton(QDialogButtonBox.StandardButton.Close)
        btn_close.clicked.connect(dlg.close)
        layout.addWidget(btn_box)

        dlg.exec()

    # ── Undo / Redo ────────────────────────────────────────────

    def _on_undo(self):
        if not self._history or not self._history.can_undo:
            return
        doc = self._history.undo()
        if doc:
            self._log_status(f"Undo → {self._history.current_label}")
            self._update_undo_redo()

    def _on_redo(self):
        if not self._history or not self._history.can_redo:
            return
        doc = self._history.redo()
        if doc:
            self._log_status(f"Redo → {self._history.current_label}")
            self._update_undo_redo()

    def _on_export(self, fmt: str):
        if not self._dxf_path:
            QMessageBox.warning(self, "No File", "Open a DXF file first.")
            return

        filters = {
            "dxf": "DXF Files (*.dxf)",
            "png": "PNG Images (*.png)",
            "pdf": "PDF Documents (*.pdf)",
            "dwg": "DWG Files (*.dwg)",
        }
        suffix = f".{fmt}"
        default_name = self._dxf_path.with_suffix(suffix)

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export as {fmt.upper()}",
            str(default_name),
            filters.get(fmt, "All Files (*)"),
        )
        if not output_path:
            return

        try:
            if fmt == "dxf":
                import shutil

                shutil.copy2(str(self._dxf_path), output_path)
                self._log_status(f"Exported DXF to: {output_path}")

            elif fmt == "png":
                try:
                    from ..core.renderer import render_dxf_to_png

                    result = render_dxf_to_png(self._dxf_path, output_path)
                    if result.success:
                        self._log_status(f"Exported PNG to: {output_path}")
                    else:
                        QMessageBox.warning(self, "Export", f"Export issue: {result.error}")
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Missing Renderer",
                        "PNG export requires the draw extra.\n"
                        "Install with: pip install -e '.[draw]'",
                    )

            elif fmt == "pdf":
                try:
                    from ..core.renderer import render_dxf_to_pdf

                    result = render_dxf_to_pdf(self._dxf_path, output_path)
                    if result.success:
                        self._log_status(f"Exported PDF to: {output_path}")
                    else:
                        QMessageBox.warning(self, "Export", f"Export issue: {result.error}")
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Missing Renderer",
                        "PDF export requires the draw extra.\n"
                        "Install with: pip install -e '.[draw]'",
                    )

            elif fmt == "dwg":
                try:
                    from ezdxf.addons import odafc

                    if not odafc.is_installed():  # type: ignore[attr-defined]
                        QMessageBox.warning(
                            self,
                            "ODA Not Found",
                            "DWG export requires ODA File Converter.\n"
                            "Download free from:\n"
                            "https://www.opendesign.com/guestfiles/oda_file_converter",
                        )
                    else:
                        import ezdxf

                        doc = ezdxf.readfile(str(self._dxf_path))
                        odafc.export_dwg(doc, str(output_path))  # type: ignore[attr-defined]
                        self._log_status(f"Exported DWG to: {output_path}")
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Missing ODA",
                        "DWG export requires ezdxf with ODA File Converter.",
                    )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Export failed:\n{e}")
            logger.error("Export error: %s", traceback.format_exc())

    # ── Window lifecycle ───────────────────────────────────────

    def closeEvent(self, event):  # noqa: N802
        self._cancel_worker()
        super().closeEvent(event)
