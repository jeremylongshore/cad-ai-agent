"""Work progress model for persistent session state.

Saved alongside documents in GCS so users can resume where they left off
after session expiry or browser close.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkProgress(BaseModel):
    """Snapshot of work-in-progress state for a document.

    Stored at ``documents/{tenant_id}/{user_id}/{doc_id}/work_progress.json``.
    Captures conversation history, audit trail, and edit state so that
    a new session can restore context after the previous one expired.
    """

    user_id: str
    doc_id: str
    tenant_id: str = ""
    saved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    edit_count: int = 0
    last_prompt: str = ""
    has_working_dxf: bool = False
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_labels: list[str] = Field(default_factory=list)
