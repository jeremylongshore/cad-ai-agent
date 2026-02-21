# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for cad-dxf-agent Windows desktop application.

Build with:
    pyinstaller installer/cad-dxf-agent.spec --noconfirm

Produces a one-dir bundle (~80-120 MB) in dist/cad-dxf-agent/
"""

import sys
from pathlib import Path

block_cipher = None

# Project root (one level up from installer/)
ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

a = Analysis(
    [str(SRC / "cad_dxf_agent" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        # Include sample files for testing
        (str(ROOT / "samples"), "samples"),
    ],
    hiddenimports=[
        "cad_dxf_agent",
        "cad_dxf_agent.app",
        "cad_dxf_agent.settings",
        "cad_dxf_agent.otel",
        "cad_dxf_agent.core",
        "cad_dxf_agent.core.dxf_reader",
        "cad_dxf_agent.core.dxf_writer",
        "cad_dxf_agent.core.edit_engine",
        "cad_dxf_agent.core.edit_history",
        "cad_dxf_agent.core.entity_index",
        "cad_dxf_agent.core.semantic_model",
        "cad_dxf_agent.core.validators",
        "cad_dxf_agent.core.preview_model",
        "cad_dxf_agent.core.revision_notes",
        "cad_dxf_agent.models",
        "cad_dxf_agent.models.cad_schema",
        "cad_dxf_agent.models.ops_schema",
        "cad_dxf_agent.models.config_schema",
        "cad_dxf_agent.models.changes_schema",
        "cad_dxf_agent.llm",
        "cad_dxf_agent.llm.planner",
        "cad_dxf_agent.llm.providers",
        "cad_dxf_agent.llm.mock_provider",
        "cad_dxf_agent.llm.agent_provider",
        "cad_dxf_agent.llm.proxy_client",
        "cad_dxf_agent.llm.tool_definitions",
        "cad_dxf_agent.llm.tool_executor",
        "cad_dxf_agent.llm.vision_describer",
        "cad_dxf_agent.llm.prompt_templates",
        "cad_dxf_agent.llm.response_parser",
        "cad_dxf_agent.ui",
        "cad_dxf_agent.ui.main_window",
        "ezdxf",
        "pydantic",
        "numpy",
        "dotenv",
        "PySide6",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "test",
        "unittest",
        "pytest",
        "mypy",
        "ruff",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cad-dxf-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — PySide6 GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: add icon when design is ready
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="cad-dxf-agent",
)
