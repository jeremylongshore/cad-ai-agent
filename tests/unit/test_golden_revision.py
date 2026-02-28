"""Golden tests for revision comparison pipeline.

Runs the ComparisonEngine on each fixture pair and compares the output
against committed expected.json files.  If the pipeline changes behavior,
these tests fail — forcing explicit review via UPDATE_GOLDENS=1.

Golden files live alongside each fixture:
    tests/fixtures/revision/<fixture>/expected.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cad_dxf_agent.core.comparison.engine import ComparisonEngine

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "revision"
UPDATE_GOLDENS = os.environ.get("UPDATE_GOLDENS", "").strip() in ("1", "true", "yes")


def _result_to_comparable(result) -> dict:
    """Convert ComparisonResult to a deterministic, comparable dict.

    Strips non-deterministic fields (DXF handles vary per ezdxf run)
    but preserves all classification logic: categories, entity types,
    layers, displacements, modifications, confidence, match methods.
    """
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
            "entity_type": (c.master_snapshot or c.revision_snapshot).entity_type.value,
            "layer": (c.master_snapshot or c.revision_snapshot).layer,
            "confidence": round(c.confidence, 4) if c.confidence is not None else None,
            "match_method": c.match_method.value if c.match_method else None,
        }

        if c.displacement:
            entry["displacement"] = {
                "x": round(c.displacement.x, 4),
                "y": round(c.displacement.y, 4),
            }

        if c.modifications:
            entry["modifications"] = c.modifications

        # Include point counts and text for debugging, but not raw handles
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


def _discover_fixtures() -> list[tuple[str, Path]]:
    """Find all fixture directories that have master.dxf + revision.dxf."""
    fixtures = []
    for p in sorted(FIXTURES_DIR.rglob("master.dxf")):
        fixture_dir = p.parent
        if (fixture_dir / "revision.dxf").exists():
            # Use relative path from fixtures dir as test ID
            rel = fixture_dir.relative_to(FIXTURES_DIR)
            fixtures.append((str(rel), fixture_dir))
    return fixtures


FIXTURE_PARAMS = _discover_fixtures()


@pytest.fixture(scope="module")
def engine():
    return ComparisonEngine()


@pytest.mark.parametrize(
    "fixture_name,fixture_dir",
    FIXTURE_PARAMS,
    ids=[f[0] for f in FIXTURE_PARAMS],
)
def test_golden_revision(fixture_name, fixture_dir, engine):
    """Compare pipeline output against golden expected.json."""
    master = fixture_dir / "master.dxf"
    revision = fixture_dir / "revision.dxf"
    golden = fixture_dir / "expected.json"

    result = engine.compare(master, revision)
    actual = _result_to_comparable(result)

    if UPDATE_GOLDENS:
        golden.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n")
        pytest.skip(f"Golden updated: {golden}")
        return

    if not golden.exists():
        # Auto-generate on first run
        golden.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n")
        pytest.fail(
            f"Golden file did not exist — auto-generated {golden}. Review and re-run to confirm."
        )

    expected = json.loads(golden.read_text())

    assert actual["summary"] == expected["summary"], (
        f"Summary mismatch for {fixture_name}:\n"
        f"  actual:   {actual['summary']}\n"
        f"  expected: {expected['summary']}"
    )
    assert actual["change_count"] == expected["change_count"], (
        f"Change count mismatch for {fixture_name}: "
        f"{actual['change_count']} != {expected['change_count']}"
    )
    assert actual["changes"] == expected["changes"], (
        f"Changes mismatch for {fixture_name}. Run UPDATE_GOLDENS=1 pytest to accept new behavior."
    )
