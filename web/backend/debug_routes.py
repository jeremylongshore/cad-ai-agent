"""OTel trace debug endpoints — only active under CAD_WEB_DEV_MODE=1.

Exposes captured spans from an InMemorySpanExporter so integration tests
and local debugging sessions can inspect trace data without a full
observability backend.

Routes:
    GET    /api/debug/traces  — Return all captured spans as JSON
    DELETE /api/debug/traces  — Clear all captured spans
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/debug", tags=["debug"])

# Set by calling set_exporter() during app startup (dev mode only).
# Remains None in production — endpoints return 503 when unset.
_exporter: Any = None


def set_exporter(exporter: Any) -> None:
    """Register the InMemorySpanExporter instance to expose via the debug API.

    Call this once during application startup when CAD_WEB_DEV_MODE is active.
    The exporter must implement ``get_finished_spans()`` and ``clear()``, matching
    the ``opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter``
    interface.
    """
    global _exporter
    _exporter = exporter


def _require_exporter() -> Any:
    """Return the exporter or raise 503 if not configured."""
    if _exporter is None:
        raise HTTPException(
            status_code=503,
            detail="Debug traces not available (OTEL not configured)",
        )
    return _exporter


def _format_span(span: Any) -> dict[str, Any]:
    """Convert an OTel ReadableSpan to a JSON-serialisable dict."""
    ctx = span.context
    parent_span_id: str | None = None
    if span.parent is not None:
        parent_span_id = format(span.parent.span_id, "016x")

    duration_ns: int | None = None
    if span.start_time is not None and span.end_time is not None:
        duration_ns = span.end_time - span.start_time

    return {
        "name": span.name,
        "trace_id": format(ctx.trace_id, "032x") if ctx else None,
        "span_id": format(ctx.span_id, "016x") if ctx else None,
        "parent_span_id": parent_span_id,
        "start_time": span.start_time,
        "end_time": span.end_time,
        "duration_ns": duration_ns,
        "status": span.status.status_code.name if span.status else None,
        "attributes": dict(span.attributes) if span.attributes else {},
    }


# ---------------------------------------------------------------------------
# GET /api/debug/traces
# ---------------------------------------------------------------------------


@router.get("/traces")
def get_traces() -> dict[str, Any]:
    """Return all captured OTel spans as JSON.

    Each span includes name, trace_id, span_id, parent_span_id,
    start_time, end_time, duration_ns, status, and attributes.

    Returns 503 if the exporter has not been configured.
    """
    exporter = _require_exporter()
    spans = exporter.get_finished_spans()
    return {
        "count": len(spans),
        "spans": [_format_span(s) for s in spans],
    }


# ---------------------------------------------------------------------------
# DELETE /api/debug/traces
# ---------------------------------------------------------------------------


@router.delete("/traces")
def clear_traces() -> dict[str, str]:
    """Clear all captured OTel spans from the in-memory exporter.

    Returns 503 if the exporter has not been configured.
    """
    exporter = _require_exporter()
    exporter.clear()
    return {"status": "cleared"}
