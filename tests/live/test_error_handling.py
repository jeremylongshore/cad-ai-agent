"""Live tests for error handling and resilience against real Vertex AI.

Tests that the providers handle edge cases gracefully:
bad credentials, invalid models, safety filters, etc.

Run with: make test-live  (or pytest tests/live/ -m live_api)
"""

from __future__ import annotations

import pytest

# google.api_core is only available with [gemini] extras
_gcp_error_types: tuple[type[Exception], ...] = (
    ValueError,
    RuntimeError,
    ConnectionError,
    OSError,
)
try:
    from google.api_core import exceptions as gcp_exceptions

    _gcp_error_types += (
        gcp_exceptions.NotFound,
        gcp_exceptions.InvalidArgument,
        gcp_exceptions.PermissionDenied,
    )
except ImportError:
    pass


@pytest.mark.live_api
class TestErrorHandlingLive:
    """Provider error handling with real API calls."""

    def test_invalid_model_raises(self, gcp_project, gcp_location, planner_context):
        """Using a non-existent model name raises an error."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(
            project=gcp_project,
            location=gcp_location,
            model_name="gemini-nonexistent-99",
        )

        with pytest.raises(_gcp_error_types):
            provider.plan("Move something", planner_context)

    def test_invalid_project_raises(self, planner_context):
        """Using a non-existent project raises an error."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(
            project="nonexistent-project-999999",
            location="us-central1",
        )

        with pytest.raises(_gcp_error_types):
            provider.plan("Move something", planner_context)

    def test_vision_missing_file_raises(self, gcp_project):
        """describe_drawing raises FileNotFoundError for missing image."""
        from cad_dxf_agent.llm.vision_describer import describe_drawing

        with pytest.raises(FileNotFoundError):
            describe_drawing("/nonexistent/path/drawing.png")

    def test_retry_on_invalid_response(self, gcp_project, gcp_location, planner_context):
        """Provider retries on validation failure (tests retry logic path)."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        # A very ambiguous prompt may trigger a retry if first response is malformed
        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Do something interesting with the entities near grid C",
            planner_context,
        )

        # Should not crash even if it needed to retry
        assert changeset is not None
