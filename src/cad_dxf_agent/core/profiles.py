"""Save, load, and list ComparisonProfile presets and user profiles."""

from __future__ import annotations

from pathlib import Path

from cad_dxf_agent.models.comparison_schema import ComparisonProfile
from cad_dxf_agent.settings import settings

BUILTIN_PROFILES: dict[str, ComparisonProfile] = {
    "structural": ComparisonProfile.structural(),
    "all": ComparisonProfile.all_entities(),
}

_BUILTIN_NAMES = frozenset(BUILTIN_PROFILES)


def _default_user_dir() -> Path:
    return settings.data_dir / "profiles"


def list_profiles(user_dir: Path | None = None) -> dict[str, ComparisonProfile]:
    """Return builtin profiles merged with any user-saved JSON profiles.

    User profiles with the same name as a builtin are ignored (builtins win).
    """
    result = dict(BUILTIN_PROFILES)
    directory = user_dir if user_dir is not None else _default_user_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            name = path.stem
            if name not in _BUILTIN_NAMES:
                result[name] = ComparisonProfile.model_validate_json(path.read_text())
    return result


def load_profile(name: str, user_dir: Path | None = None) -> ComparisonProfile:
    """Load a profile by name — builtins first, then user directory.

    Raises:
        KeyError: If no profile with that name exists.
    """
    if name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]

    directory = user_dir if user_dir is not None else _default_user_dir()
    path = directory / f"{name}.json"
    if path.is_file():
        return ComparisonProfile.model_validate_json(path.read_text())

    raise KeyError(f"Profile not found: {name!r}")


def save_profile(profile: ComparisonProfile, user_dir: Path | None = None) -> Path:
    """Save a profile to the user directory as JSON.

    Raises:
        ValueError: If the profile name collides with a builtin.
    """
    if profile.name in _BUILTIN_NAMES:
        raise ValueError(
            f"Cannot overwrite builtin profile {profile.name!r}. "
            f"Choose a different name."
        )

    directory = user_dir if user_dir is not None else _default_user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile.name}.json"
    path.write_text(profile.model_dump_json(indent=2))
    return path
