#!/usr/bin/env python3
"""Fail when generated frontend trees leak into Python distributions."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PATHS = (
    "/web/frontend/node_modules/",
    "/web/frontend/dist/",
)


def find_forbidden_members(names: list[str]) -> list[str]:
    """Return archive members that belong to generated frontend trees."""
    return [name for name in names if any(path in f"/{name}" for path in FORBIDDEN_PATHS)]


def archive_members(path: Path) -> list[str]:
    """Read member names from a wheel/zip or compressed source archive."""
    if path.suffix == ".whl" or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as archive:
            return archive.getnames()
    raise ValueError(f"unsupported distribution archive: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist_dir", nargs="?", type=Path, default=Path("dist"))
    args = parser.parse_args()

    archives = sorted(args.dist_dir.glob("*.whl")) + sorted(args.dist_dir.glob("*.tar.gz"))
    if not archives:
        parser.error(f"no wheel or source archive found in {args.dist_dir}")

    failures: list[str] = []
    for archive in archives:
        forbidden = find_forbidden_members(archive_members(archive))
        if forbidden:
            sample = ", ".join(forbidden[:3])
            failures.append(f"{archive}: {len(forbidden)} generated members ({sample})")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print(f"Distribution manifests clean: {len(archives)} archive(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
