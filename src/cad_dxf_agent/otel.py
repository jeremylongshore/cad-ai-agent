"""OpenTelemetry bootstrap — initializes tracing when OTEL_ENABLED is set.

All imports are guarded so the app works fine without OTel installed.
When disabled, get_tracer() returns a no-op tracer and span() is a passthrough.
"""

from __future__ import annotations

import contextlib
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_otel_initialized = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def init_otel(service_name: str = "cad-dxf-agent") -> None:
    """Initialize OpenTelemetry tracing.

    No-op if OTEL_ENABLED env var is not truthy or if OTel is not installed.
    Safe to call multiple times — only the first call takes effect.
    """
    global _otel_initialized

    if _otel_initialized:
        return

    if not _HAS_OTEL:
        logger.debug("OpenTelemetry packages not installed, tracing disabled")
        return

    from .settings import settings

    if not settings.otel_enabled:
        logger.debug("OpenTelemetry disabled (OTEL_ENABLED not set)")
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
            logger.info("OTel: using OTLP exporter → %s", settings.otel_endpoint)
        except ImportError:
            logger.warning("OTel: OTLP exporter not installed, falling back to console")
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()
        logger.info("OTel: using console exporter")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _otel_initialized = True
    logger.info("OpenTelemetry tracing initialized (service=%s)", service_name)


def init_otel_testing(exporter: Any) -> None:
    """Initialize OTel with a caller-supplied exporter (for tests).

    Uses a SimpleSpanProcessor for immediate export.
    """
    global _otel_initialized

    if not _HAS_OTEL:
        return

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    resource = Resource.create({"service.name": "cad-dxf-agent-test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _otel_initialized = True


def reset_otel() -> None:
    """Reset OTel state (for test teardown)."""
    global _otel_initialized
    _otel_initialized = False

    if not _HAS_OTEL:
        return

    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        with contextlib.suppress(Exception):
            provider.shutdown()

    # Reset to default no-op provider
    trace.set_tracer_provider(trace.NoOpTracerProvider())


def get_tracer(name: str = "cad-dxf-agent") -> Any:
    """Return an OTel tracer. Returns a no-op tracer if OTel is not available."""
    if not _HAS_OTEL:
        return _NoOpTracer()

    return trace.get_tracer(name)


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Any, None, None]:
    """Context manager wrapper for ergonomic span usage.

    Yields the span (or a no-op object if OTel is disabled).
    """
    tracer = get_tracer()
    if isinstance(tracer, _NoOpTracer):
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, v)
        yield s


class _NoOpSpan:
    """Minimal stand-in when OTel is not installed."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpTracer:
    """Minimal stand-in tracer when OTel is not installed."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()
