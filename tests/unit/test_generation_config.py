"""Tests for LLM generation config settings flow."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestGenerationConfigSettings:
    """Verify generation config settings parse correctly from env vars."""

    def test_default_temperature(self):
        with patch.dict(os.environ, {}, clear=False):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_temperature == 0.0

    def test_custom_temperature(self):
        with patch.dict(os.environ, {"CAD_LLM_TEMPERATURE": "0.7"}):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_temperature == 0.7

    def test_default_top_p_is_none(self):
        with patch.dict(os.environ, {}, clear=False):
            # Ensure CAD_LLM_TOP_P is not set
            env = {k: v for k, v in os.environ.items() if k != "CAD_LLM_TOP_P"}
            with patch.dict(os.environ, env, clear=True):
                from cad_dxf_agent.settings import Settings

                s = Settings()
                assert s.llm_top_p is None

    def test_custom_top_p(self):
        with patch.dict(os.environ, {"CAD_LLM_TOP_P": "0.95"}):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_top_p == 0.95

    def test_default_top_k_is_none(self):
        env = {k: v for k, v in os.environ.items() if k != "CAD_LLM_TOP_K"}
        with patch.dict(os.environ, env, clear=True):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_top_k is None

    def test_custom_top_k(self):
        with patch.dict(os.environ, {"CAD_LLM_TOP_K": "40"}):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_top_k == 40

    def test_default_max_output_tokens(self):
        with patch.dict(os.environ, {}, clear=False):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_max_output_tokens == 4096

    def test_custom_max_output_tokens(self):
        with patch.dict(os.environ, {"CAD_LLM_MAX_OUTPUT_TOKENS": "8192"}):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.llm_max_output_tokens == 8192


class TestPlannerSettings:
    """Verify planner timeout/retry settings parse correctly."""

    def test_default_planner_timeout(self):
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.planner_timeout == 60

    def test_custom_planner_timeout(self):
        with patch.dict(os.environ, {"CAD_PLANNER_TIMEOUT": "120"}):
            from cad_dxf_agent.settings import Settings

            s = Settings()
            assert s.planner_timeout == 120

    def test_default_planner_max_retries(self):
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.planner_max_retries == 2

    def test_default_planner_retry_delay(self):
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.planner_retry_delay == 1.0
