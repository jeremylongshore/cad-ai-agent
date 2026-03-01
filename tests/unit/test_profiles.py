"""Tests for profile persistence (save/load/list)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.profiles import (
    BUILTIN_PROFILES,
    list_profiles,
    load_profile,
    save_profile,
)
from cad_dxf_agent.models.comparison_schema import ComparisonProfile


class TestBuiltinProfiles:
    def test_builtin_profiles_available(self) -> None:
        assert "structural" in BUILTIN_PROFILES
        assert "all" in BUILTIN_PROFILES

    def test_load_builtin(self) -> None:
        profile = load_profile("structural")
        assert profile.name == "structural"
        assert len(profile.exclude_layers) > 0

    def test_load_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError, match="no-such-profile"):
            load_profile("no-such-profile", user_dir=tmp_path)


class TestSaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        custom = ComparisonProfile(
            name="my-custom",
            description="Custom test profile",
            exclude_layers=[r"(?i)^junk"],
            tolerance=0.5,
        )
        path = save_profile(custom, user_dir=tmp_path)
        assert path.exists()
        assert path.name == "my-custom.json"

        loaded = load_profile("my-custom", user_dir=tmp_path)
        assert loaded.name == custom.name
        assert loaded.description == custom.description
        assert loaded.exclude_layers == custom.exclude_layers
        assert loaded.tolerance == custom.tolerance

    def test_save_builtin_name_rejected(self, tmp_path: Path) -> None:
        for name in ("structural", "all"):
            profile = ComparisonProfile(name=name)
            with pytest.raises(ValueError, match="builtin"):
                save_profile(profile, user_dir=tmp_path)

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        v1 = ComparisonProfile(name="evolving", description="version 1")
        save_profile(v1, user_dir=tmp_path)

        v2 = ComparisonProfile(name="evolving", description="version 2")
        save_profile(v2, user_dir=tmp_path)

        loaded = load_profile("evolving", user_dir=tmp_path)
        assert loaded.description == "version 2"


class TestListProfiles:
    def test_list_includes_builtins(self, tmp_path: Path) -> None:
        profiles = list_profiles(user_dir=tmp_path)
        assert "structural" in profiles
        assert "all" in profiles

    def test_list_includes_user_profiles(self, tmp_path: Path) -> None:
        custom = ComparisonProfile(name="user-one", description="User profile")
        save_profile(custom, user_dir=tmp_path)

        profiles = list_profiles(user_dir=tmp_path)
        assert "user-one" in profiles
        assert profiles["user-one"].description == "User profile"
        # Builtins still present
        assert "structural" in profiles
