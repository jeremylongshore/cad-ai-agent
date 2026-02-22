"""Conftest for live API tests — skips unless GCP credentials are available.

Project detection order:
  1. CAD_GCP_PROJECT env var (set in CI via GitHub Actions vars)
  2. google.auth.default() ADC auto-detection (local dev)

Local dev: `gcloud auth application-default login`
CI: WIF via google-github-actions/auth@v2 (tokenless)
"""

from __future__ import annotations

import os

import pytest

LIVE_API_REASON = (
    "Live API tests require Application Default Credentials. "
    "Run: gcloud auth application-default login"
)


def _detect_gcp_project() -> str | None:
    """Auto-detect GCP project: env var first, then ADC."""
    project = os.getenv("CAD_GCP_PROJECT")
    if project:
        return project
    try:
        import google.auth  # type: ignore[import-untyped]

        _, project = google.auth.default()
        return project
    except Exception:
        return None


def pytest_collection_modifyitems(config, items):
    """Auto-skip live_api tests when ADC is not available."""
    if _detect_gcp_project() is not None:
        return  # ADC works, don't skip anything
    skip_live = pytest.mark.skip(reason=LIVE_API_REASON)
    for item in items:
        if "live_api" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def gcp_project():
    """Return the GCP project ID auto-detected from ADC."""
    project = _detect_gcp_project()
    if not project:
        pytest.skip(LIVE_API_REASON)
    return project


@pytest.fixture
def gcp_location():
    """Return the GCP location (default: us-central1)."""
    return os.getenv("CAD_GCP_LOCATION", "us-central1")


@pytest.fixture
def structural_drawing(tmp_path):
    """Create a realistic structural drawing for live tests."""
    from tests.helpers.dxf_factory import create_structural_drawing

    return create_structural_drawing(tmp_path)


@pytest.fixture
def structural_context(structural_drawing):
    """Load the structural drawing into a DrawingContext."""
    from cad_dxf_agent.core.dxf_reader import load_dxf

    return load_dxf(structural_drawing)


@pytest.fixture
def planner_context(structural_context):
    """Build a planner context dict from the structural drawing."""
    from cad_dxf_agent.core.semantic_model import build_planner_context

    return build_planner_context(structural_context)
