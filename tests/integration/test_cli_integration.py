"""Integration tests for CLI main() — end-to-end via argv."""

from __future__ import annotations

import json

import pytest

from cad_dxf_agent.cli.main import main
from tests.helpers.comparison_factory import (
    make_complex_pair,
    make_identical_pair,
    make_moved_entity_pair,
)


@pytest.mark.integration
class TestMainEntryPoint:
    def test_no_command_returns_2(self):
        rc = main([])
        assert rc == 2

    def test_diff_identical_returns_0(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        rc = main(["diff", str(master), str(revision)])
        assert rc == 0

    def test_diff_changes_returns_1(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path)
        rc = main(["diff", str(master), str(revision)])
        assert rc == 1

    def test_compare_alias_works(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        rc = main(["compare", str(master), str(revision)])
        assert rc == 0

    def test_diff_json_flag(self, tmp_path, capsys):
        master, revision = make_moved_entity_pair(tmp_path)
        main(["--json", "diff", str(master), str(revision)])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "summary" in data

    def test_missing_file_returns_2(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        rc = main(["diff", str(master), "/nonexistent/file.dxf"])
        assert rc == 2

    def test_explain_returns_changelog(self, tmp_path, capsys):
        master, revision = make_complex_pair(tmp_path)
        rc = main(["explain", str(master), str(revision)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "CHANGE LOG" in out

    def test_apply_creates_output(self, tmp_path):
        dxf_dir = tmp_path / "dxf"
        dxf_dir.mkdir()
        master, revision = make_moved_entity_pair(dxf_dir)
        output = tmp_path / "result.dxf"
        rc = main(
            [
                "apply",
                str(master),
                str(revision),
                "--output",
                str(output),
                "--approve-all",
            ]
        )
        assert rc == 1
        assert output.exists()

    def test_bundle_creates_run_metadata(self, tmp_path):
        dxf_dir = tmp_path / "dxf"
        dxf_dir.mkdir()
        master, revision = make_moved_entity_pair(dxf_dir)
        out_dir = tmp_path / "bundle"
        rc = main(
            [
                "bundle",
                str(master),
                str(revision),
                "--output-dir",
                str(out_dir),
                "--approve-all",
            ]
        )
        assert rc == 1
        assert (out_dir / "run_metadata.json").exists()
        meta = json.loads((out_dir / "run_metadata.json").read_text())
        assert "run_id" in meta

    def test_dry_run_shows_ops(self, tmp_path, capsys):
        master, revision = make_moved_entity_pair(tmp_path)
        rc = main(["dry-run", str(master), str(revision)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "Operations" in out

    def test_align_identical(self, tmp_path, capsys):
        master, revision = make_identical_pair(tmp_path)
        rc = main(["align", str(master), str(revision)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Method:" in out

    def test_verbose_flag(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        rc = main(["-v", "diff", str(master), str(revision)])
        assert rc == 0
