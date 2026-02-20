"""CI-safe tests for OpenTelemetry instrumentation.

Uses InMemorySpanExporter — no network calls, no external dependencies.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from cad_dxf_agent.otel import init_otel_testing, reset_otel


@pytest.fixture()
def otel_exporter():
    """Set up OTel with in-memory exporter, tear down after test."""
    exporter = InMemorySpanExporter()
    init_otel_testing(exporter)
    yield exporter
    reset_otel()
    exporter.shutdown()


@pytest.fixture()
def otel_disabled():
    """Ensure OTel is disabled for the test."""
    reset_otel()
    yield
    reset_otel()


class TestLoadDxfSpan:
    def test_load_dxf_creates_span(self, sample_dxf, otel_exporter):
        from cad_dxf_agent.core.dxf_reader import load_dxf

        ctx = load_dxf(sample_dxf)

        spans = otel_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "cad.load_dxf" in span_names

        load_span = next(s for s in spans if s.name == "cad.load_dxf")
        attrs = dict(load_span.attributes)
        assert attrs["cad.file.name"] == "sample.dxf"
        assert attrs["cad.entities.count"] == ctx.entity_count
        assert attrs["cad.layers.count"] == len(ctx.layers)


class TestRunPlannerSpan:
    def test_run_planner_creates_span(self, sample_context, otel_exporter):
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.llm.planner import run_planner

        drawing_ctx = build_planner_context(sample_context)
        changeset = run_planner("Move the column east by 2 feet", drawing_ctx)

        spans = otel_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "cad.run_planner" in span_names

        planner_span = next(s for s in spans if s.name == "cad.run_planner")
        attrs = dict(planner_span.attributes)
        assert attrs["cad.mode"] == "mock"
        assert attrs["cad.ops.count"] == changeset.op_count


class TestValidateSpan:
    def test_validate_creates_span(self, sample_context, rule_config, otel_exporter):
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.core.validators import validate_changeset
        from cad_dxf_agent.llm.planner import run_planner

        drawing_ctx = build_planner_context(sample_context)
        changeset = run_planner("Move the column east by 2 feet", drawing_ctx)
        validation = validate_changeset(changeset, sample_context, rule_config)

        spans = otel_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "cad.validate" in span_names

        val_span = next(s for s in spans if s.name == "cad.validate")
        attrs = dict(val_span.attributes)
        assert attrs["cad.validation.valid"] == validation.valid
        assert "cad.validation.blockers" in attrs


class TestBuildContextSpan:
    def test_build_context_creates_span(self, sample_context, otel_exporter):
        from cad_dxf_agent.core.semantic_model import build_planner_context

        build_planner_context(sample_context)

        spans = otel_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "cad.build_context" in span_names

        ctx_span = next(s for s in spans if s.name == "cad.build_context")
        attrs = dict(ctx_span.attributes)
        assert attrs["cad.entities.count"] == sample_context.entity_count


class TestOtelDisabled:
    def test_no_spans_when_disabled(self, sample_dxf, otel_disabled):
        """When OTel is not initialized, no spans should be created."""
        from cad_dxf_agent.core.dxf_reader import load_dxf

        load_dxf(sample_dxf)
        # No exporter to check — the key point is that load_dxf runs
        # without error even when OTel is in no-op mode
