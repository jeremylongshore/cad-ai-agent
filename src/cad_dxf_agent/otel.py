"""OpenTelemetry bootstrap — initializes tracing and metrics when OTEL_ENABLED is set.

All imports are guarded so the app works fine without OTel installed.
When disabled, get_tracer() returns a no-op tracer, get_meter() returns a no-op
meter, and span() is a passthrough.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Internal provider references — avoids the global set_*_provider limitation
_provider: Any = None
_meter_provider: Any = None

try:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def init_otel(service_name: str = "cad-dxf-agent") -> None:
    """Initialize OpenTelemetry tracing and metrics.

    No-op if OTEL_ENABLED env var is not truthy or if OTel is not installed.
    Safe to call multiple times — only the first call takes effect.
    """
    global _provider, _meter_provider

    if _provider is not None:
        return

    if not _HAS_OTEL:
        logger.debug("OpenTelemetry packages not installed, tracing/metrics disabled")
        return

    from .settings import settings

    if not settings.otel_enabled:
        logger.debug("OpenTelemetry disabled (OTEL_ENABLED not set)")
        return

    resource = Resource.create({"service.name": service_name})

    # --- Tracer provider ---
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter == "gcp-trace":
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            span_exporter = CloudTraceSpanExporter()
            logger.info("OTel: using Google Cloud Trace exporter")
        except ImportError:
            logger.warning("OTel: gcp-trace exporter not installed, falling back to console")
            span_exporter = ConsoleSpanExporter()
    elif settings.otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            span_exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
            logger.info("OTel: using OTLP exporter → %s", settings.otel_endpoint)
        except ImportError:
            logger.warning("OTel: OTLP exporter not installed, falling back to console")
            span_exporter = ConsoleSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()
        logger.info("OTel: using console exporter")

    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    _provider = provider

    # --- Meter provider ---
    if settings.otel_exporter == "gcp-trace":
        try:
            from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter

            metric_exporter: Any = CloudMonitoringMetricsExporter()
            logger.info("OTel: using Cloud Monitoring metrics exporter")
        except ImportError:
            logger.warning(
                "OTel: cloud_monitoring exporter not installed, falling back to console metrics"
            )
            metric_exporter = ConsoleMetricExporter()
    elif settings.otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(endpoint=settings.otel_endpoint)
            logger.info("OTel: using OTLP metrics exporter → %s", settings.otel_endpoint)
        except ImportError:
            logger.warning(
                "OTel: OTLP metrics exporter not installed, falling back to console metrics"
            )
            metric_exporter = ConsoleMetricExporter()
    else:
        metric_exporter = ConsoleMetricExporter()
        logger.info("OTel: using console metrics exporter")

    reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    _meter_provider = meter_provider

    import atexit

    atexit.register(provider.shutdown)
    atexit.register(meter_provider.shutdown)

    logger.info("OpenTelemetry initialized (service=%s)", service_name)


def init_otel_testing(exporter: Any, metric_exporter: Any | None = None) -> None:
    """Initialize OTel with caller-supplied exporters (for tests).

    Uses a SimpleSpanProcessor for immediate span export.
    When metric_exporter is None, a ConsoleMetricExporter is used as a stand-in.
    """
    global _provider, _meter_provider

    if not _HAS_OTEL:
        return

    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    resource = Resource.create({"service.name": "cad-dxf-agent-test"})

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _provider = provider

    chosen_metric_exporter = (
        metric_exporter if metric_exporter is not None else ConsoleMetricExporter()
    )
    reader = PeriodicExportingMetricReader(chosen_metric_exporter)
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])


def reset_otel() -> None:
    """Reset OTel state (for test teardown)."""
    global _provider, _meter_provider

    if _provider is not None and hasattr(_provider, "shutdown"):
        with contextlib.suppress(Exception):
            _provider.shutdown()
    _provider = None

    if _meter_provider is not None and hasattr(_meter_provider, "shutdown"):
        with contextlib.suppress(Exception):
            _meter_provider.shutdown()
    _meter_provider = None


def get_tracer(name: str = "cad-dxf-agent") -> Any:
    """Return a lazy tracer that delegates to the current provider.

    Returns a no-op tracer if OTel is not installed. If OTel is installed but
    not yet initialized, the tracer will produce no-op spans until init is called.
    """
    if not _HAS_OTEL:
        return _NoOpTracer()

    return _LazyTracer(name)


def get_meter(name: str = "cad-dxf-agent") -> Any:
    """Return a lazy meter that delegates to the current meter provider.

    Returns a no-op meter if OTel is not installed. If OTel is installed but
    not yet initialized, the meter will return no-op instruments until init is called.
    """
    if not _HAS_OTEL:
        return _NoOpMeter()

    return _LazyMeter(name)


def create_metrics(meter_name: str = "cad-dxf-agent") -> dict[str, Any]:
    """Create and return the standard set of cad-dxf-agent instruments.

    Call once at application startup and share the returned dict across modules.
    All instruments are no-ops when OTel is not installed or not initialized.

    Returns:
        dict with keys:
            - ``request_count`` — Counter, total requests processed
            - ``request_latency`` — Histogram, request latency in milliseconds
            - ``agent_turns`` — Histogram, agent turns per request
            - ``tool_call_success`` — Counter, successful tool calls
            - ``tool_call_failure`` — Counter, failed tool calls
    """
    meter = get_meter(meter_name)
    return {
        "request_count": meter.create_counter(
            "cad.request.count",
            description="Total requests processed",
        ),
        "request_latency": meter.create_histogram(
            "cad.request.latency_ms",
            description="Request latency in milliseconds",
            unit="ms",
        ),
        "agent_turns": meter.create_histogram(
            "cad.agent.turns",
            description="Agent turns per request",
        ),
        "tool_call_success": meter.create_counter(
            "cad.tool.success",
            description="Successful tool calls",
        ),
        "tool_call_failure": meter.create_counter(
            "cad.tool.failure",
            description="Failed tool calls",
        ),
    }


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Any, None, None]:
    """Context manager wrapper for ergonomic span usage.

    Yields the span (or a no-op object if OTel is disabled).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, v)
        yield s


# ---------------------------------------------------------------------------
# Lazy delegates
# ---------------------------------------------------------------------------


class _LazyTracer:
    """Tracer that delegates to the current _provider at call time.

    This ensures module-level ``tracer = get_tracer(__name__)`` works correctly
    even if OTel is initialized after import.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Generator[Any, None, None]:
        if _provider is not None:
            real_tracer = _provider.get_tracer(self._name)
            with real_tracer.start_as_current_span(name, **kwargs) as s:
                yield s
        else:
            yield _NoOpSpan()


class _LazyMeter:
    """Meter that delegates to the current _meter_provider at call time.

    This ensures module-level ``meter = get_meter(__name__)`` works correctly
    even if OTel is initialized after import.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def _real_meter(self) -> Any:
        if _meter_provider is not None:
            return _meter_provider.get_meter(self._name)
        return _NoOpMeter()

    def create_counter(self, name: str, **kwargs: Any) -> Any:
        return self._real_meter().create_counter(name, **kwargs)

    def create_histogram(self, name: str, **kwargs: Any) -> Any:
        return self._real_meter().create_histogram(name, **kwargs)


# ---------------------------------------------------------------------------
# No-op stand-ins
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Minimal stand-in when OTel is not installed or not initialized."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def record_exception(
        self, exception: BaseException, attributes: dict[str, Any] | None = None
    ) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass


class _NoOpTracer:
    """Minimal stand-in tracer when OTel is not installed."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()


class _NoOpCounter:
    """No-op counter instrument."""

    def add(self, amount: int | float, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpHistogram:
    """No-op histogram instrument."""

    def record(self, amount: int | float, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpMeter:
    """Minimal stand-in meter when OTel is not installed or not initialized."""

    def create_counter(self, name: str, **kwargs: Any) -> _NoOpCounter:
        return _NoOpCounter()

    def create_histogram(self, name: str, **kwargs: Any) -> _NoOpHistogram:
        return _NoOpHistogram()
