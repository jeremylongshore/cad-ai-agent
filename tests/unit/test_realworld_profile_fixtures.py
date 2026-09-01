"""Integrity checks for the real-world AEC persona E2E corpus."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "tests/fixtures/realworld_profile_conversations.json"


def _profiles() -> list[dict[str, object]]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def test_realworld_profile_corpus_has_expected_document_coverage() -> None:
    profiles = _profiles()
    fixtures = [profile["drawing_fixture"] for profile in profiles]

    assert len(profiles) == 25
    assert len(set(fixtures)) == 23
    assert sum(path.endswith(".dxf") for path in fixtures) == 20
    assert sum(path.endswith(".pdf") for path in fixtures) == 5
    assert len({path for path in fixtures if path.endswith(".pdf")}) == 4
    assert all((ROOT / path).is_file() for path in fixtures)


def test_realworld_profile_corpus_identifies_two_heyflora_workflows() -> None:
    profiles = _profiles()
    heyflora = [
        profile
        for profile in profiles
        if "HeyFlora.ai" in profile["title"] and "HeyFlora.ai" in profile["profile"]["context"]
    ]

    assert [profile["id"] for profile in heyflora] == ["profile-15", "profile-25"]
