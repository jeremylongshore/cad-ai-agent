"""DXF file writer — saves modified drawings as new DXF files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import ezdxf

logger = logging.getLogger(__name__)


def save_as_new_dxf(
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Save a modified DXF as a new file. Never overwrites the source.

    Returns the output path on success.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    if output_path.resolve() == source_path.resolve():
        raise ValueError("Output path must differ from source path (save-as workflow).")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.readfile(str(source_path))
    doc.saveas(str(output_path))

    logger.info("Saved modified DXF to: %s", output_path)
    return output_path


def copy_dxf_for_editing(source_path: str | Path, work_path: str | Path) -> Path:
    """Copy source DXF to a working path for in-memory editing.

    Used internally so the original is never touched.
    """
    source_path = Path(source_path)
    work_path = Path(work_path)

    if work_path.resolve() == source_path.resolve():
        raise ValueError("Work path must differ from source path.")

    work_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, work_path)
    return work_path
