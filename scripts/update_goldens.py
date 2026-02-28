#!/usr/bin/env python3
"""Regenerate all golden expected.json files for revision fixtures.

Usage:
    python scripts/update_goldens.py

Or equivalently:
    UPDATE_GOLDENS=1 pytest tests/unit/test_golden_revision.py -v

Review the diffs before committing — goldens encode pipeline behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cad_dxf_agent.core.comparison.engine import ComparisonEngine  # noqa: E402

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "revision"


def _result_to_comparable(result) -> dict:
    """Same logic as test_golden_revision._result_to_comparable."""
    changes = []
    for c in sorted(
        result.changes,
        key=lambda ch: (
            ch.category.value,
            (ch.master_snapshot or ch.revision_snapshot).layer,
            (ch.master_snapshot or ch.revision_snapshot).entity_type.value,
        ),
    ):
        entry = {
            "category": c.category.value,
            "entity_type": (
                c.master_snapshot or c.revision_snapshot
            ).entity_type.value,
            "layer": (c.master_snapshot or c.revision_snapshot).layer,
            "confidence": (
                round(c.confidence, 4) if c.confidence is not None else None
            ),
            "match_method": (
                c.match_method.value if c.match_method else None
            ),
        }
        if c.displacement:
            entry["displacement"] = {
                "x": round(c.displacement.x, 4),
                "y": round(c.displacement.y, 4),
            }
        if c.modifications:
            entry["modifications"] = c.modifications
        snap = c.master_snapshot or c.revision_snapshot
        entry["point_count"] = len(snap.points) if snap.points else 0
        if snap.text_content:
            entry["text_content"] = snap.text_content
        if snap.block_name:
            entry["block_name"] = snap.block_name
        changes.append(entry)

    return {
        "summary": result.summary,
        "change_count": len(result.changes),
        "changes": changes,
    }


def main() -> None:
    engine = ComparisonEngine()
    updated = 0

    for master in sorted(FIXTURES_DIR.rglob("master.dxf")):
        fixture_dir = master.parent
        revision = fixture_dir / "revision.dxf"
        if not revision.exists():
            continue

        rel = fixture_dir.relative_to(FIXTURES_DIR)
        result = engine.compare(master, revision)
        golden = fixture_dir / "expected.json"
        golden.write_text(
            json.dumps(
                _result_to_comparable(result), indent=2, ensure_ascii=False
            )
            + "\n"
        )
        updated += 1
        print(f"  Updated {rel}/expected.json")

    print(f"\n{updated} golden files updated. Review diffs before committing.")


if __name__ == "__main__":
    main()
