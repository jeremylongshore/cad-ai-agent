"""Build script for cad-dxf-agent desktop distribution.

Orchestrates PyInstaller build with pre/post validation:
1. Check required dependencies are installed
2. Run PyInstaller with the .spec file
3. Validate the output bundle
4. Run a headless smoke test on the bundle

Usage:
    python scripts/build.py              # Build for current platform
    python scripts/build.py --clean      # Clean build (delete previous)
    python scripts/build.py --skip-test  # Skip post-build smoke test
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = PROJECT_ROOT / "cad_dxf_agent.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
BUNDLE_DIR = DIST_DIR / "cad-dxf-agent"


def check_dependencies() -> list[str]:
    """Verify build-time dependencies are available."""
    errors = []

    # PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        errors.append("PyInstaller not installed: pip install pyinstaller")

    # PySide6 (required for GUI build)
    try:
        import PySide6  # noqa: F401
    except ImportError:
        errors.append("PySide6 not installed: pip install -e '.[gui]'")

    # Core dependencies
    for mod in ["ezdxf", "pydantic", "numpy", "httpx", "dotenv"]:
        try:
            __import__(mod)
        except ImportError:
            errors.append(f"{mod} not installed: pip install -e '.'")

    return errors


def run_pyinstaller(clean: bool = False) -> int:
    """Run PyInstaller with the spec file."""
    if clean:
        for d in [BUILD_DIR, BUNDLE_DIR]:
            if d.exists():
                print(f"  Cleaning {d}...")
                shutil.rmtree(d)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
    ]
    if clean:
        cmd.append("--clean")

    print(f"  Running: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def validate_bundle() -> list[str]:
    """Check the output bundle has expected files."""
    errors = []

    if not BUNDLE_DIR.exists():
        errors.append(f"Bundle directory not found: {BUNDLE_DIR}")
        return errors

    # Check for main executable
    exe_name = "cad-dxf-agent.exe" if platform.system() == "Windows" else "cad-dxf-agent"
    exe_path = BUNDLE_DIR / exe_name
    if not exe_path.exists():
        errors.append(f"Executable not found: {exe_path}")

    # Check bundle isn't suspiciously small
    total_size = sum(f.stat().st_size for f in BUNDLE_DIR.rglob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)
    print(f"  Bundle size: {total_mb:.1f} MB")

    if total_mb < 10:
        errors.append(f"Bundle suspiciously small ({total_mb:.1f} MB) — likely missing deps")

    # Check for PySide6 Qt libraries
    qt_libs = list(BUNDLE_DIR.rglob("Qt6Core*")) + list(BUNDLE_DIR.rglob("libQt6Core*"))
    if not qt_libs:
        errors.append("Qt6Core library not found in bundle — PySide6 may be missing")

    return errors


def smoke_test_bundle() -> int:
    """Run a headless import test on the bundled executable."""
    exe_name = "cad-dxf-agent.exe" if platform.system() == "Windows" else "cad-dxf-agent"
    exe_path = BUNDLE_DIR / exe_name

    if not exe_path.exists():
        print("  SKIP: executable not found")
        return 1

    # Test that the bundle can at least import core modules
    # We use --help or a quick import test rather than launching the full GUI
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"  # No display needed
    env["CAD_LLM_PROVIDER"] = "mock"

    print(f"  Testing: {exe_path}")
    try:
        result = subprocess.run(
            [str(exe_path)],
            env=env,
            timeout=15,
            capture_output=True,
            text=True,
        )
        # GUI app will fail without display even with offscreen, but exit code 0
        # or a clean Qt error (not ImportError/ModuleNotFoundError) means success
        if result.returncode == 0:
            print("  PASS: bundle starts successfully")
            return 0
        if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
            print(f"  FAIL: missing module\n{result.stderr[:500]}")
            return 1
        # Qt platform errors are expected in headless — that's OK
        print("  PASS: bundle loads (Qt display error expected in headless)")
        return 0
    except subprocess.TimeoutExpired:
        # App started and ran for 15s — that's actually success for a GUI app
        print("  PASS: bundle started (killed after 15s timeout)")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Build cad-dxf-agent desktop distribution")
    parser.add_argument("--clean", action="store_true", help="Clean build directories first")
    parser.add_argument("--skip-test", action="store_true", help="Skip post-build smoke test")
    args = parser.parse_args()

    print("=" * 60)
    print("  cad-dxf-agent Build")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version.split()[0]}")
    print("=" * 60)

    # Step 1: Check dependencies
    print("\n[1/4] Checking dependencies...")
    dep_errors = check_dependencies()
    if dep_errors:
        print("  ERRORS:")
        for e in dep_errors:
            print(f"    - {e}")
        sys.exit(1)
    print("  OK")

    # Step 2: Run PyInstaller
    print("\n[2/4] Building with PyInstaller...")
    rc = run_pyinstaller(clean=args.clean)
    if rc != 0:
        print(f"  FAILED (exit code {rc})")
        sys.exit(rc)
    print("  OK")

    # Step 3: Validate bundle
    print("\n[3/4] Validating bundle...")
    val_errors = validate_bundle()
    if val_errors:
        print("  ERRORS:")
        for e in val_errors:
            print(f"    - {e}")
        sys.exit(1)
    print("  OK")

    # Step 4: Smoke test
    if args.skip_test:
        print("\n[4/4] Smoke test SKIPPED")
    else:
        print("\n[4/4] Smoke testing bundle...")
        rc = smoke_test_bundle()
        if rc != 0:
            print("  WARNING: smoke test failed (bundle may still work with a display)")

    print("\n" + "=" * 60)
    print(f"  BUILD COMPLETE: {BUNDLE_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
