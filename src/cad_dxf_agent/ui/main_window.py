"""Main desktop window — PySide6 shell for the DXF editing workflow.

Full-featured desktop UI for Tony's structural drawing edits:
- File open (DXF/DWG/PDF with format detection)
- Layout/space selector
- Prompt input with history
- Per-operation approve/reject checkboxes
- Undo/redo (Ctrl+Z / Ctrl+Y)
- Export menu (DXF, PNG, PDF)
- Status bar with entity count and layer info
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
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
from ..core.edit_engine import EditEngine
from ..core.edit_history import EditHistory
from ..core.preview_model import PreviewModel
from ..core.revision_notes import insert_revision_note
from ..core.semantic_model import build_planner_context
from ..core.validators import validate_changeset
from ..llm.planner import run_planner
from ..models.config_schema import RevisionNoteConfig, RuleConfig
from ..models.ops_schema import ChangeSet, EditOperation
from ..settings import settings

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

    # ── Event handlers ────────────────────────────────────────────

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open CAD File", "", FILE_FILTER)
        if not path:
            return

        try:
            file_path = Path(path)

            # DWG/PDF conversion if needed
            if file_path.suffix.lower() in (".dwg", ".pdf"):
                try:
                    from ..core.converter import convert_to_dxf

                    result = convert_to_dxf(file_path)
                    if result.success:
                        file_path = result.output_path
                        self._log_status(f"Converted {path} to DXF")
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
            self._changeset = None
            self._preview = None
            self._clear_ops()
            self._update_undo_redo()

            # Populate layout selector
            self.cmb_layout.clear()
            for layout in self._context.layouts:
                self.cmb_layout.addItem(f"{layout.name} ({layout.entity_count})")
            self.cmb_layout.setEnabled(len(self._context.layouts) > 1)

            # Update status bar
            self.lbl_entity_count.setText(f"Entities: {self._context.entity_count}")
            self.lbl_layer_count.setText(f"Layers: {len(self._context.layers)}")

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

        try:
            self._log_status(f"Planning: {prompt[:60]}...")
            drawing_ctx = build_planner_context(self._context)
            self._changeset = run_planner(prompt, drawing_ctx)

            validation = validate_changeset(self._changeset, self._context, self._rule_config)
            self._preview = PreviewModel(self._changeset, self._context, validation)

            # Build per-operation checkboxes
            self._clear_ops()
            for item in self._preview.items:
                cb = QCheckBox(str(item))
                cb.setChecked(True)
                self._op_checkboxes.append(cb)
                self.ops_layout.addWidget(cb)

            if not validation.valid:
                for b in validation.blockers:
                    lbl = QLabel(f"BLOCKED: {b.message}")
                    lbl.setStyleSheet("color: red; font-weight: bold;")
                    self.ops_layout.addWidget(lbl)
                self._log_status(f"Plan blocked: {len(validation.blockers)} issue(s)")
                self.btn_apply.setEnabled(False)
            else:
                self._log_status(f"Plan valid: {self._changeset.op_count} operation(s)")
                self.btn_apply.setEnabled(True)

            for w in validation.warnings:
                self._log_status(f"Warning: {w.message}")

        except Exception as e:
            QMessageBox.critical(self, "Planner Error", f"Planning failed:\n{e}")
            logger.error("Planner error: %s", traceback.format_exc())

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

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As New DXF",
            str(self._dxf_path.with_stem(self._dxf_path.stem + "_edited")),
            "DXF Files (*.dxf)",
        )
        if not output_path:
            return

        try:
            filtered = ChangeSet(
                prompt=self._changeset.prompt,
                operations=selected_ops,
                revision_label=self._changeset.revision_label,
            )

            engine = EditEngine(self._dxf_path)
            results = engine.apply_changeset(filtered)

            # Capture snapshot for undo before saving
            if self._history:
                self._history.push(
                    engine.doc,
                    f"Applied {len(selected_ops)} op(s)",
                )
                self._update_undo_redo()

            engine.save(output_path)

            success_count = sum(1 for r in results if r.success)
            self._log_status(f"Applied {success_count}/{len(results)} operations")

            # Insert revision note if enabled
            if self._rev_config.enabled:
                note_text = insert_revision_note(
                    output_path, output_path, results, self._rev_config
                )
                self._log_status(f"Revision note: {note_text}")

            self._log_status(f"Saved to: {output_path}")
            QMessageBox.information(self, "Success", f"Saved to:\n{output_path}")

        except Exception as e:
            QMessageBox.critical(self, "Apply Error", f"Apply/save failed:\n{e}")
            logger.error("Apply error: %s", traceback.format_exc())

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

            elif fmt in ("png", "pdf"):
                try:
                    from ..core.renderer import render_dxf

                    result = render_dxf(
                        self._dxf_path,
                        output_format=fmt,
                        output_path=output_path,
                    )
                    if result.success:
                        self._log_status(f"Exported {fmt.upper()} to: {output_path}")
                    else:
                        QMessageBox.warning(self, "Export", f"Export issue: {result.error}")
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Missing Renderer",
                        f"{fmt.upper()} export requires the draw extra.\n"
                        "Install with: pip install -e '.[draw]'",
                    )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Export failed:\n{e}")
            logger.error("Export error: %s", traceback.format_exc())
