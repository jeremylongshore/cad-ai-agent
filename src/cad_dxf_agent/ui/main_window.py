"""Main desktop window — PySide6 shell for the DXF editing workflow."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.dxf_reader import load_dxf
from ..core.edit_engine import EditEngine
from ..core.preview_model import PreviewModel
from ..core.revision_notes import insert_revision_note
from ..core.semantic_model import build_planner_context
from ..core.validators import validate_changeset
from ..llm.planner import run_planner
from ..models.config_schema import RevisionNoteConfig, RuleConfig
from ..settings import settings

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary application window for cad-dxf-agent."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("cad-dxf-agent — DXF Layout Editor")
        self.setMinimumSize(900, 600)

        self._dxf_path: Path | None = None
        self._context = None
        self._changeset = None
        self._preview = None
        self._rule_config = RuleConfig(protected_layers=settings.protected_layers)
        self._rev_config = RevisionNoteConfig(
            enabled=settings.revision_notes_enabled,
            layer_name=settings.revision_notes_layer,
        )

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # Left panel: controls
        left = QVBoxLayout()

        # Open DXF
        self.btn_open = QPushButton("Open DXF")
        self.btn_open.clicked.connect(self._on_open)
        left.addWidget(self.btn_open)

        self.lbl_file = QLabel("No file loaded")
        left.addWidget(self.lbl_file)

        # Prompt
        left.addWidget(QLabel("Prompt:"))
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setMaximumHeight(100)
        self.txt_prompt.setPlaceholderText("Describe the edit you want to make...")
        left.addWidget(self.txt_prompt)

        # Plan / Preview
        self.btn_plan = QPushButton("Plan && Preview")
        self.btn_plan.setEnabled(False)
        self.btn_plan.clicked.connect(self._on_plan)
        left.addWidget(self.btn_plan)

        # Apply / Save
        self.btn_apply = QPushButton("Apply && Save As...")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        left.addWidget(self.btn_apply)

        # Status
        left.addWidget(QLabel("Status:"))
        self.txt_status = QTextEdit()
        self.txt_status.setReadOnly(True)
        self.txt_status.setMaximumHeight(120)
        left.addWidget(self.txt_status)

        left.addStretch()
        main_layout.addLayout(left, 1)

        # Right panel: operations list
        right = QVBoxLayout()
        right.addWidget(QLabel("Operations:"))
        self.lst_ops = QListWidget()
        right.addWidget(self.lst_ops)
        main_layout.addLayout(right, 1)

    def _log_status(self, msg: str):
        self.txt_status.append(msg)
        logger.info(msg)

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DXF File", "", "DXF Files (*.dxf);;All Files (*)"
        )
        if not path:
            return

        try:
            self._dxf_path = Path(path)
            self._context = load_dxf(self._dxf_path)
            self.lbl_file.setText(f"{self._dxf_path.name} ({self._context.entity_count} entities)")
            self.btn_plan.setEnabled(True)
            self.btn_apply.setEnabled(False)
            self._changeset = None
            self._preview = None
            self.lst_ops.clear()
            self._log_status(f"Loaded: {self._dxf_path.name}")
            if self._context.unsupported_entity_types:
                self._log_status(
                    f"Skipped types: {', '.join(self._context.unsupported_entity_types)}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load DXF:\n{e}")
            logger.error("DXF load error: %s", traceback.format_exc())

    def _on_plan(self):
        if not self._context:
            return

        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "No Prompt", "Enter a prompt describing the edit.")
            return

        try:
            self._log_status(f"Planning: {prompt[:60]}...")
            drawing_ctx = build_planner_context(self._context)
            self._changeset = run_planner(prompt, drawing_ctx)

            validation = validate_changeset(self._changeset, self._context, self._rule_config)
            self._preview = PreviewModel(self._changeset, self._context, validation)

            self.lst_ops.clear()
            for item in self._preview.items:
                self.lst_ops.addItem(str(item))

            if validation.valid:
                self._log_status(f"Plan valid: {self._changeset.op_count} operation(s)")
                self.btn_apply.setEnabled(True)
            else:
                for b in validation.blockers:
                    self.lst_ops.addItem(f"BLOCKED: {b.message}")
                self._log_status(f"Plan blocked: {len(validation.blockers)} issue(s)")
                self.btn_apply.setEnabled(False)

            for w in validation.warnings:
                self._log_status(f"Warning: {w.message}")

        except Exception as e:
            QMessageBox.critical(self, "Planner Error", f"Planning failed:\n{e}")
            logger.error("Planner error: %s", traceback.format_exc())

    def _on_apply(self):
        if not self._changeset or not self._dxf_path:
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
            engine = EditEngine(self._dxf_path)
            results = engine.apply_changeset(self._changeset)
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
