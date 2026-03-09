"""User document models for persistent document storage.

Defines UserDocument — the metadata model for permanently stored user drawings.
Documents live in GCS under per-user paths and appear in the document library.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserDocument(BaseModel):
    """A permanently stored user document.

    Represents a DXF file uploaded to the user's personal library.
    The actual file lives in GCS; this model tracks metadata only.
    """

    user_id: str
    doc_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    filename: str
    upload_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_accessed: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    gcs_path: str = ""
    file_size_bytes: int = 0
    status: Literal["active", "deleted"] = "active"
    tenant_id: str = ""
    has_work_progress: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update last_accessed to now."""
        self.last_accessed = datetime.now(UTC).isoformat()
