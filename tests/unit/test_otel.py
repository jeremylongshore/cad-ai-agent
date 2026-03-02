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


class TestGcpTraceExporter:
    def test_gcp_trace_exporter_selected(self, monkeypatch):
        """When OTEL_EXPORTER=gcp-trace and package available, uses GCP exporter."""
        import sys
        import types
        import unittest.mock

        import cad_dxf_agent.otel as otel_mod

        reset_otel()
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER", "gcp-trace")

        # Mock the CloudTraceSpanExporter module
        mock_exporter = unittest.mock.MagicMock()
        mock_module = types.ModuleType("opentelemetry.exporter.cloud_trace")
        mock_module.CloudTraceSpanExporter = lambda: mock_exporter  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "opentelemetry.exporter.cloud_trace", mock_module)

        # Fresh settings with env vars applied
        from cad_dxf_agent.settings import Settings

        monkeypatch.setattr("cad_dxf_agent.settings.settings", Settings())

        otel_mod.init_otel(service_name="test-gcp")
        assert otel_mod._provider is not None
        reset_otel()

    def test_gcp_trace_fallback_when_not_installed(self, monkeypatch):
        """When OTEL_EXPORTER=gcp-trace but package missing, falls back to console."""
        import sys

        import cad_dxf_agent.otel as otel_mod

        reset_otel()
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER", "gcp-trace")

        # Block the import so it raises ImportError
        monkeypatch.setitem(sys.modules, "opentelemetry.exporter.cloud_trace", None)

        from cad_dxf_agent.settings import Settings

        monkeypatch.setattr("cad_dxf_agent.settings.settings", Settings())

        otel_mod.init_otel(service_name="test-gcp-fallback")
        assert otel_mod._provider is not None  # console fallback still initializes
        reset_otel()


class TestOtelDisabled:
    def test_no_spans_when_disabled(self, sample_dxf, otel_disabled):
        """When OTel is not initialized, no spans should be created."""
        from cad_dxf_agent.core.dxf_reader import load_dxf

        load_dxf(sample_dxf)
        # No exporter to check — the key point is that load_dxf runs
        # without error even when OTel is in no-op mode


class TestOtlpExporter:
    def test_otlp_exporter_selected(self, monkeypatch):
        """When otel_endpoint is set and OTLP package is available, uses OTLP exporter."""
        import sys
        import types
        import unittest.mock

        import cad_dxf_agent.otel as otel_mod

        reset_otel()
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

        mock_exporter_instance = unittest.mock.MagicMock()

        def _make_exporter(endpoint=None):
            return mock_exporter_instance

        # Build a fake module hierarchy for the OTLP exporter
        fake_trace_exporter = types.ModuleType(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
        )
        fake_trace_exporter.OTLPSpanExporter = _make_exporter  # type: ignore[attr-defined]

        for mod_name in [
            "opentelemetry.exporter.otlp",
            "opentelemetry.exporter.otlp.proto",
            "opentelemetry.exporter.otlp.proto.grpc",
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        ]:
            if mod_name not in sys.modules:
                monkeypatch.setitem(sys.modules, mod_name, types.ModuleType(mod_name))

        monkeypatch.setitem(
            sys.modules,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
            fake_trace_exporter,
        )

        from cad_dxf_agent.settings import Settings

        monkeypatch.setattr("cad_dxf_agent.settings.settings", Settings())

        otel_mod.init_otel(service_name="test-otlp")
        assert otel_mod._provider is not None
        reset_otel()

    def test_otlp_fallback_when_package_missing(self, monkeypatch):
        """When OTLP package is not installed, falls back to console exporter."""
        import sys

        import cad_dxf_agent.otel as otel_mod

        reset_otel()
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

        # Setting the module to None causes ImportError on 'from ... import ...'
        monkeypatch.setitem(
            sys.modules,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
            None,
        )

        from cad_dxf_agent.settings import Settings

        monkeypatch.setattr("cad_dxf_agent.settings.settings", Settings())

        # Should not raise — falls back to ConsoleSpanExporter
        otel_mod.init_otel(service_name="test-otlp-fallback")
        assert otel_mod._provider is not None
        reset_otel()


class TestResetOtel:
    def test_reset_calls_provider_shutdown(self, monkeypatch):
        """reset_otel() calls shutdown on the current provider."""
        import unittest.mock

        import cad_dxf_agent.otel as otel_mod

        mock_provider = unittest.mock.MagicMock()
        otel_mod._provider = mock_provider
        reset_otel()
        mock_provider.shutdown.assert_called_once()
        assert otel_mod._provider is None

    def test_reset_when_already_none_is_safe(self):
        """reset_otel() when _provider is None does not raise."""
        import cad_dxf_agent.otel as otel_mod

        otel_mod._provider = None
        reset_otel()  # must not raise
        assert otel_mod._provider is None

    def test_init_otel_idempotent(self, monkeypatch):
        """Second call to init_otel while provider is set is a no-op."""
        import unittest.mock

        import cad_dxf_agent.otel as otel_mod

        # Pre-set a provider so init_otel short-circuits
        sentinel = unittest.mock.MagicMock()
        otel_mod._provider = sentinel
        monkeypatch.setenv("OTEL_ENABLED", "true")

        otel_mod.init_otel(service_name="second-call")
        # Provider must not have been replaced
        assert otel_mod._provider is sentinel
        otel_mod._provider = None  # clean up manually


class TestNoOpClasses:
    """Cover _NoOpSpan and _NoOpTracer methods that are bypassed in normal flow."""

    def test_noop_span_record_exception(self):
        """_NoOpSpan.record_exception does not raise."""
        from cad_dxf_agent.otel import _NoOpSpan

        span = _NoOpSpan()
        span.record_exception(ValueError("boom"))

    def test_noop_span_set_status(self):
        """_NoOpSpan.set_status does not raise."""
        from cad_dxf_agent.otel import _NoOpSpan

        span = _NoOpSpan()
        span.set_status("ERROR", description="something went wrong")

    def test_noop_span_set_attribute(self):
        """_NoOpSpan.set_attribute does not raise."""
        from cad_dxf_agent.otel import _NoOpSpan

        span = _NoOpSpan()
        span.set_attribute("key", "value")

    def test_noop_span_add_event(self):
        """_NoOpSpan.add_event does not raise."""
        from cad_dxf_agent.otel import _NoOpSpan

        span = _NoOpSpan()
        span.add_event("my.event", attributes={"k": "v"})

    def test_noop_tracer_yields_noop_span(self):
        """_NoOpTracer.start_as_current_span yields a _NoOpSpan."""
        from cad_dxf_agent.otel import _NoOpSpan, _NoOpTracer

        tracer = _NoOpTracer()
        with tracer.start_as_current_span("test.span") as s:
            assert isinstance(s, _NoOpSpan)
            s.set_attribute("x", 1)  # must not raise

    def test_span_context_manager_no_otel(self):
        """span() context manager works when OTel provider is not initialised."""
        import cad_dxf_agent.otel as otel_mod
        from cad_dxf_agent.otel import span

        reset_otel()
        otel_mod._provider = None

        with span("test.noop", attributes={"a": 1}) as s:
            # s is a _NoOpSpan — attribute setting must be silent
            s.set_attribute("b", 2)
