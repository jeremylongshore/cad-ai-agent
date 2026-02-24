"""Tests for planner retry with exponential backoff."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cad_dxf_agent.llm.errors import PlannerRetryExhaustedError
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.llm.providers import PlannerProvider
from cad_dxf_agent.models.ops_schema import ChangeSet


class FailNTimesProvider(PlannerProvider):
    """Mock provider that fails N times then succeeds."""

    def __init__(self, fail_count: int = 2) -> None:
        self._fail_count = fail_count
        self._attempts = 0

    @property
    def name(self) -> str:
        return "fail-n-mock"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise ValueError(f"Simulated failure #{self._attempts}")
        return ChangeSet(prompt=prompt, operations=[])


class AlwaysFailProvider(PlannerProvider):
    """Mock provider that always fails."""

    @property
    def name(self) -> str:
        return "always-fail"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        raise RuntimeError("Permanent failure")


@patch("cad_dxf_agent.llm.planner.settings")
class TestPlannerRetry:
    def _setup_settings(self, mock_settings, max_retries=2, delay=0.0):
        mock_settings.planner_timeout = 30
        mock_settings.planner_max_retries = max_retries
        mock_settings.planner_retry_delay = delay
        mock_settings.llm_provider = "mock"

    def test_succeeds_after_one_failure(self, mock_settings):
        self._setup_settings(mock_settings, max_retries=2)
        provider = FailNTimesProvider(fail_count=1)
        result = run_planner("test", {}, provider=provider)
        assert isinstance(result, ChangeSet)
        assert provider._attempts == 2

    def test_exhausts_retries(self, mock_settings):
        self._setup_settings(mock_settings, max_retries=2)
        provider = AlwaysFailProvider()
        with pytest.raises(PlannerRetryExhaustedError) as exc_info:
            run_planner("test", {}, provider=provider)
        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_error, RuntimeError)

    def test_single_retry_succeeds_on_first_try(self, mock_settings):
        self._setup_settings(mock_settings, max_retries=1)
        provider = FailNTimesProvider(fail_count=0)
        result = run_planner("test", {}, provider=provider)
        assert isinstance(result, ChangeSet)
        assert provider._attempts == 1

    def test_retry_exhausted_error_message(self, mock_settings):
        err = PlannerRetryExhaustedError(3, ValueError("bad json"))
        assert "3 attempt(s)" in str(err)
        assert "bad json" in str(err)
        assert err.attempts == 3

    def test_retry_exhausted_error_no_last_error(self, mock_settings):
        err = PlannerRetryExhaustedError(2)
        assert "2 attempt(s)" in str(err)
        assert err.last_error is None
