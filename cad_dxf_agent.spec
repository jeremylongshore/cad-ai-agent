# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for cad-dxf-agent desktop application.

Builds a single-directory distribution with all required dependencies:
- PySide6 (Qt 6 runtime, plugins, translations)
- ezdxf (DXF parsing, resources)
- pydantic (validation, compiled core)
- numpy (array operations)

Usage:
    pyinstaller cad_dxf_agent.spec          # Build from project root
    pyinstaller cad_dxf_agent.spec --clean   # Clean build

Output:
    dist/cad-dxf-agent/                     # Single-directory bundle
    dist/cad-dxf-agent/cad-dxf-agent.exe    # Entry point (Windows)
    dist/cad-dxf-agent/cad-dxf-agent        # Entry point (Linux)
"""

import sys
from pathlib import Path

block_cipher = None

# Project root is where the spec file lives
PROJECT_ROOT = Path(SPECPATH)
SRC_ROOT = PROJECT_ROOT / "src"

# ── Data files to include ──────────────────────────────────────────
# Collect non-Python files needed at runtime.
datas = []

# ezdxf resources (icons, fallback templates)
try:
    import ezdxf
    ezdxf_root = Path(ezdxf.__file__).parent
    ezdxf_resources = ezdxf_root / "resources"
    if ezdxf_resources.exists():
        datas.append((str(ezdxf_resources), "ezdxf/resources"))
except ImportError:
    pass

# .env.example for reference (not .env itself — never bundle secrets)
env_example = PROJECT_ROOT / ".env.example"
if env_example.exists():
    datas.append((str(env_example), "."))

# ── Hidden imports ─────────────────────────────────────────────────
# Modules that PyInstaller's analysis misses because they're loaded
# dynamically (lazy imports, plugins, provider pattern).
hiddenimports = [
    # Core dependencies
    "ezdxf",
    "ezdxf.addons",
    "ezdxf.entities",
    "ezdxf.layouts",
    "ezdxf.sections",
    "pydantic",
    "pydantic.deprecated.decorator",
    "pydantic._internal._validators",
    "pydantic._internal._core_utils",
    "numpy",
    "numpy.core._methods",
    "numpy.core._dtype_ctypes",
    "httpx",
    "httpx._transports.default",
    "dotenv",
    # App modules loaded via lazy imports
    "cad_dxf_agent.core.converter",
    "cad_dxf_agent.core.renderer",
    "cad_dxf_agent.llm.mock_provider",
    "cad_dxf_agent.llm.gemini_provider",
    "cad_dxf_agent.llm.agent_provider",
    "cad_dxf_agent.llm.proxy_client",
    "cad_dxf_agent.llm.gemini_key_provider",
    "cad_dxf_agent.otel",
]

# Optional: Google Cloud / Gemini (include if installed)
try:
    import google.cloud.aiplatform  # noqa: F401
    hiddenimports.extend([
        "google.cloud.aiplatform",
        "google.auth",
        "google.auth.transport.requests",
        "vertexai",
        "vertexai.generative_models",
    ])
except ImportError:
    pass

# Optional: google-generativeai (API key provider, no GCP needed)
try:
    import google.generativeai  # noqa: F401
    hiddenimports.extend([
        "google.generativeai",
    ])
except ImportError:
    pass

# Optional: OpenTelemetry (include if installed)
try:
    import opentelemetry  # noqa: F401
    hiddenimports.extend([
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.trace.export",
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    ])
except ImportError:
    pass

# Optional: matplotlib for rendering (include if installed)
try:
    import matplotlib  # noqa: F401
    hiddenimports.append("matplotlib.backends.backend_agg")
except ImportError:
    pass

# ── Analysis ───────────────────────────────────────────────────────
a = Analysis(
    [str(SRC_ROOT / "cad_dxf_agent" / "app.py")],
    pathex=[str(SRC_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev/test dependencies — not needed in production
        "pytest",
        "pytest_cov",
        "syrupy",
        "ruff",
        "mypy",
        "pre_commit",
        "pip_audit",
        "bandit",
        # Exclude unused stdlib modules to reduce bundle size
        "tkinter",
        "unittest",
        "xmlrpc",
        "test",
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
    console=False,  # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: add app icon (.ico for Windows, .icns for macOS)
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
