"""Benchmark tests for Gemini API latency and cost tracking.

Measures round-trip time for each provider type and reports results.
Not meant to fail — purely informational metrics.

Run with: make test-live  (or pytest tests/live/ -m live_api -s)
"""

from __future__ import annotations

import time

import pytest


@pytest.mark.live_api
class TestBenchmarkLive:
    """Latency benchmarks for live Gemini calls."""

    def test_oneshot_latency(self, gcp_project, gcp_location, planner_context):
        """Measure one-shot GeminiProvider round-trip time."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)

        start = time.monotonic()
        changeset = provider.plan(
            "Move the column at grid A-1 east by 24 inches",
            planner_context,
        )
        elapsed = time.monotonic() - start

        print(f"\n  One-shot latency: {elapsed:.2f}s")
        print(f"  Operations: {changeset.op_count}")

        # Soft assertion — just flag if unusually slow
        assert elapsed < 60, f"One-shot took {elapsed:.1f}s (expected <60s)"

    def test_agent_latency(self, gcp_project, gcp_location, planner_context):
        """Measure agent tool-use loop round-trip time."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project=gcp_project, location=gcp_location)

        start = time.monotonic()
        changeset = provider.plan(
            "Move the column at grid B-2 north by 12 inches",
            planner_context,
        )
        elapsed = time.monotonic() - start

        print(f"\n  Agent loop latency: {elapsed:.2f}s")
        print(f"  Operations: {changeset.op_count}")
        print(f"  Revision: {changeset.revision_label}")

        # Agent loop is slower (multiple turns), allow more time
        assert elapsed < 120, f"Agent loop took {elapsed:.1f}s (expected <120s)"
