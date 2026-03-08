"""Edit history — snapshot-based undo/redo for DXF editing.

Maintains a stack of DXF document snapshots. Each applied operation
creates a snapshot that can be reverted (undo) or re-applied (redo).
Uses ezdxf's stream I/O for efficient serialization.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import ezdxf

logger = logging.getLogger(__name__)


class EditHistory:
    """Snapshot-based undo/redo for a DXF document.

    Each call to push() captures the current document state.
    undo()/redo() navigate the snapshot stack and return the
    restored document.
    """

    def __init__(self, initial_path: str | Path, max_snapshots: int = 0) -> None:
        self._initial_path = Path(initial_path)
        self._snapshots: list[bytes] = []
        self._cursor: int = -1  # Points to current snapshot; -1 = initial
        self._labels: list[str] = []
        self._max_snapshots = max_snapshots

        # Capture the initial state
        doc = ezdxf.readfile(str(self._initial_path))
        self._initial_snapshot = _serialize(doc)

    def push(self, doc: ezdxf.document.Drawing, label: str = "") -> None:
        """Capture current document state as a new snapshot.

        Discards any redo history beyond the current cursor position.
        Evicts the oldest snapshot when max_snapshots is exceeded.
        """
        # Truncate redo stack
        self._snapshots = self._snapshots[: self._cursor + 1]
        self._labels = self._labels[: self._cursor + 1]

        snapshot = _serialize(doc)
        self._snapshots.append(snapshot)
        self._labels.append(label)
        self._cursor = len(self._snapshots) - 1

        # Evict oldest if over cap (0 = unlimited)
        if self._max_snapshots > 0 and len(self._snapshots) > self._max_snapshots:
            excess = len(self._snapshots) - self._max_snapshots
            self._snapshots = self._snapshots[excess:]
            self._labels = self._labels[excess:]
            self._cursor -= excess
            logger.debug("Evicted %d oldest snapshot(s), cap=%d", excess, self._max_snapshots)

        logger.debug(
            "Snapshot pushed [%d]: %s (%d bytes)",
            self._cursor,
            label,
            len(snapshot),
        )

    def undo(self) -> ezdxf.document.Drawing | None:
        """Undo: move cursor back one step and return the restored document.

        Returns None if already at initial state.
        """
        if self._cursor < 0:
            return None  # Already at initial state

        if self._cursor == 0:
            # Restore to initial state
            self._cursor = -1
            return _deserialize(self._initial_snapshot)

        self._cursor -= 1
        logger.debug("Undo to snapshot [%d]", self._cursor)
        return _deserialize(self._snapshots[self._cursor])

    def redo(self) -> ezdxf.document.Drawing | None:
        """Redo: move cursor forward one step and return the restored document.

        Returns None if already at the latest state.
        """
        if self._cursor >= len(self._snapshots) - 1:
            return None  # Already at latest

        self._cursor += 1
        logger.debug("Redo to snapshot [%d]", self._cursor)
        return _deserialize(self._snapshots[self._cursor])

    @property
    def can_undo(self) -> bool:
        return self._cursor >= 0

    @property
    def can_redo(self) -> bool:
        return self._cursor < len(self._snapshots) - 1

    @property
    def depth(self) -> int:
        """Total number of snapshots (not counting initial)."""
        return len(self._snapshots)

    @property
    def current_label(self) -> str:
        """Label of the current snapshot, or 'initial' if at base state."""
        if self._cursor < 0:
            return "initial"
        return self._labels[self._cursor]

    @property
    def labels(self) -> list[str]:
        """All snapshot labels (read-only copy)."""
        return list(self._labels)

    @property
    def cursor(self) -> int:
        """Current cursor position (-1 = initial state)."""
        return self._cursor

    def get_current_doc(self) -> ezdxf.document.Drawing:
        """Return the document at the current cursor position."""
        if self._cursor < 0:
            return _deserialize(self._initial_snapshot)
        return _deserialize(self._snapshots[self._cursor])


def _serialize(doc: ezdxf.document.Drawing) -> bytes:
    """Serialize a DXF document to bytes."""
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _deserialize(data: bytes) -> ezdxf.document.Drawing:
    """Deserialize a DXF document from bytes."""
    stream = io.StringIO(data.decode("utf-8"))
    return ezdxf.read(stream)
