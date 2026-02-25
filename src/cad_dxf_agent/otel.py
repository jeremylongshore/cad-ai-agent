"""OpenTelemetry bootstrap — initializes tracing when OTEL_ENABLED is set.

All imports are guarded so the app works fine without OTel installed.
When disabled, get_tracer() returns a no-op tracer and span() is a passthrough.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Internal provider reference — avoids the global set_tracer_provider limitation
_provider: Any = None

try:
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
    global _provider

    if _provider is not None:
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

    if settings.otel_exporter == "gcp-trace":
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter()
            logger.info("OTel: using Google Cloud Trace exporter")
        except ImportError:
            logger.warning(
                "OTel: gcp-trace exporter not installed, falling back to console"
            )
            exporter = ConsoleSpanExporter()
    elif settings.otel_endpoint:
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
    _provider = provider

    import atexit

    atexit.register(provider.shutdown)

    logger.info("OpenTelemetry tracing initialized (service=%s)", service_name)


def init_otel_testing(exporter: Any) -> None:
    """Initialize OTel with a caller-supplied exporter (for tests).

    Uses a SimpleSpanProcessor for immediate export.
    """
    global _provider

    if not _HAS_OTEL:
        return

    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    resource = Resource.create({"service.name": "cad-dxf-agent-test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _provider = provider


def reset_otel() -> None:
    """Reset OTel state (for test teardown)."""
    global _provider

    if _provider is not None and hasattr(_provider, "shutdown"):
        with contextlib.suppress(Exception):
            _provider.shutdown()

    _provider = None


def get_tracer(name: str = "cad-dxf-agent") -> Any:
    """Return a lazy tracer that delegates to the current provider.

    Returns a no-op tracer if OTel is not installed. If OTel is installed but
    not yet initialized, the tracer will produce no-op spans until init is called.
    """
    if not _HAS_OTEL:
        return _NoOpTracer()

    return _LazyTracer(name)


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
