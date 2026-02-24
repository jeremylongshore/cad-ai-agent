"""GUI test fixtures — offscreen QApplication."""

from __future__ import annotations

import os

# Must be set before any Qt import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """Skip GUI tests when PySide6 is not installed."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(reason="PySide6 not installed")
        for item in items:
            if "gui" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="module")
def qapp():
    """Provide a QApplication instance (one per module)."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
