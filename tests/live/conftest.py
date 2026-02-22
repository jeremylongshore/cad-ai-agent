"""Conftest for live API tests — skips unless GCP credentials are available."""

from __future__ import annotations

import os

import pytest

# The marker applied to all tests in this directory
LIVE_API_REASON = (
    "Live API tests require GOOGLE_CLOUD_PROJECT env var "
    "and valid GCP credentials (gcloud auth application-default login)"
)


def pytest_collection_modifyitems(config, items):
    """Auto-skip live_api tests when GCP credentials are not available."""
    skip_live = pytest.mark.skip(reason=LIVE_API_REASON)
    for item in items:
        if "live_api" in item.keywords and not os.getenv("GOOGLE_CLOUD_PROJECT"):
            item.add_marker(skip_live)


@pytest.fixture
def gcp_project():
    """Return the GCP project ID from environment."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
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
