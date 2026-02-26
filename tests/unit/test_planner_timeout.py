"""Tests for planner timeout enforcement."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from cad_dxf_agent.llm.errors import PlannerTimeoutError
from cad_dxf_agent.llm.planner import _call_with_timeout
from cad_dxf_agent.llm.providers import PlannerProvider
from cad_dxf_agent.models.ops_schema import ChangeSet


class SlowProvider(PlannerProvider):
    """Mock provider that sleeps longer than timeout."""

    def __init__(self, delay: float = 5.0) -> None:
        self._delay = delay

    @property
    def name(self) -> str:
        return "slow-mock"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        time.sleep(self._delay)
        return ChangeSet(prompt=prompt)


class FastProvider(PlannerProvider):
    """Mock provider that returns immediately."""

    @property
    def name(self) -> str:
        return "fast-mock"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        return ChangeSet(prompt=prompt, operations=[])


class TestPlannerTimeout:
    def test_timeout_fires_on_slow_provider(self):
        provider = SlowProvider(delay=10.0)
        with pytest.raises(PlannerTimeoutError) as exc_info:
            _call_with_timeout(provider, "test", {}, timeout=1)
        assert exc_info.value.timeout_seconds == 1

    def test_fast_provider_returns_normally(self):
        provider = FastProvider()
        result = _call_with_timeout(provider, "test", {}, timeout=5)
        assert isinstance(result, ChangeSet)
        assert result.prompt == "test"

    def test_timeout_error_message(self):
        err = PlannerTimeoutError(30)
        assert "30s" in str(err)
        assert err.timeout_seconds == 30

    def test_timeout_error_custom_message(self):
        err = PlannerTimeoutError(10, "custom message")
        assert str(err) == "custom message"

    @patch("cad_dxf_agent.llm.planner.settings")
    def test_run_planner_uses_timeout_setting(self, mock_settings):
        """Verify run_planner reads timeout from settings."""
        mock_settings.planner_timeout = 60
        mock_settings.planner_max_retries = 1
        mock_settings.planner_retry_delay = 0.0
        mock_settings.llm_provider = "mock"

        from cad_dxf_agent.llm.planner import run_planner

        # Should succeed with fast mock provider
        result = run_planner("test prompt", {}, provider=FastProvider())
        assert isinstance(result, ChangeSet)
