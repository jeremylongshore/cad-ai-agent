"""Test CLI command functions with comparison_factory DXF pairs."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from cad_dxf_agent.cli.commands import (
    cmd_apply,
    cmd_bundle,
    cmd_diff,
    cmd_explain,
)
from tests.helpers.comparison_factory import (
    make_complex_pair,
    make_identical_pair,
    make_moved_entity_pair,
)


class TestCmdDiff:
    def test_identical_returns_0(self, tmp_path, capsys):
        master, revision = make_identical_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            tolerance=1.0,
            output_dir=None,
            json=False,
            verbose=False,
        )
        rc = cmd_diff(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "unchanged" in out.lower() or "total" in out.lower()

    def test_changes_returns_1(self, tmp_path, capsys):
        master, revision = make_moved_entity_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            tolerance=1.0,
            output_dir=None,
            json=False,
            verbose=False,
        )
        rc = cmd_diff(args)
        assert rc == 1

    def test_output_dir_creates_files(self, tmp_path):
        dxf_dir = tmp_path / "dxf"
        dxf_dir.mkdir()
        master, revision = make_complex_pair(dxf_dir)
        out_dir = tmp_path / "output"
        args = Namespace(
            master=str(master),
            revision=str(revision),
            tolerance=1.0,
            output_dir=str(out_dir),
            json=False,
            verbose=False,
        )
        cmd_diff(args)
        assert (out_dir / "changelog.json").exists()
        assert (out_dir / "changelog.txt").exists()

    def test_json_output(self, tmp_path, capsys):
        master, revision = make_moved_entity_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            tolerance=1.0,
            output_dir=None,
            json=True,
            verbose=False,
        )
        cmd_diff(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "summary" in data
        assert "total_changes" in data

    def test_missing_master_raises(self, tmp_path):
        _, revision = make_identical_pair(tmp_path)
        args = Namespace(
            master="/nonexistent/master.dxf",
            revision=str(revision),
            tolerance=1.0,
            output_dir=None,
            json=False,
            verbose=False,
        )
        with pytest.raises(FileNotFoundError):
            cmd_diff(args)

    def test_missing_revision_raises(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision="/nonexistent/revision.dxf",
            tolerance=1.0,
            output_dir=None,
            json=False,
            verbose=False,
        )
        with pytest.raises(FileNotFoundError):
            cmd_diff(args)


class TestCmdApply:
    def test_apply_approve_all(self, tmp_path):
        dxf_dir = tmp_path / "dxf"
        dxf_dir.mkdir()
        master, revision = make_moved_entity_pair(dxf_dir)
        output = tmp_path / "result" / "out.dxf"
        args = Namespace(
            master=str(master),
            revision=str(revision),
            output=str(output),
            approve_all=True,
            json=False,
            verbose=False,
        )
        rc = cmd_apply(args)
        assert rc == 1  # changes applied
        assert output.exists()
        # Original master unchanged
        assert master.exists()

    def test_apply_no_changes(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        output = tmp_path / "out.dxf"
        args = Namespace(
            master=str(master),
            revision=str(revision),
            output=str(output),
            approve_all=True,
            json=False,
            verbose=False,
        )
        rc = cmd_apply(args)
        assert rc == 0


class TestCmdBundle:
    def test_bundle_creates_metadata(self, tmp_path):
        dxf_dir = tmp_path / "dxf"
        dxf_dir.mkdir()
        master, revision = make_moved_entity_pair(dxf_dir)
        out_dir = tmp_path / "bundle"
        args = Namespace(
            master=str(master),
            revision=str(revision),
            output_dir=str(out_dir),
            approve_all=True,
            json=False,
            verbose=False,
        )
        rc = cmd_bundle(args)
        assert rc == 1
        assert (out_dir / "run_metadata.json").exists()
        assert (out_dir / "changelog.json").exists()

    def test_bundle_no_changes(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        out_dir = tmp_path / "bundle"
        args = Namespace(
            master=str(master),
            revision=str(revision),
            output_dir=str(out_dir),
            approve_all=True,
            json=False,
            verbose=False,
        )
        rc = cmd_bundle(args)
        assert rc == 0


class TestCmdExplain:
    def test_explain_outputs_changelog(self, tmp_path, capsys):
        master, revision = make_moved_entity_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            json=False,
            verbose=False,
        )
        rc = cmd_explain(args)
        assert rc == 1  # changes found
        out = capsys.readouterr().out
        assert "CHANGE LOG" in out

    def test_explain_no_changes(self, tmp_path, capsys):
        master, revision = make_identical_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            json=False,
            verbose=False,
        )
        rc = cmd_explain(args)
        assert rc == 0

    def test_explain_json(self, tmp_path, capsys):
        master, revision = make_complex_pair(tmp_path)
        args = Namespace(
            master=str(master),
            revision=str(revision),
            json=True,
            verbose=False,
        )
        cmd_explain(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "entries" in data
