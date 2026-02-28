"""Test argparse structure — fast, no DXF I/O."""

from __future__ import annotations

import pytest

from cad_dxf_agent.cli.main import build_parser


@pytest.fixture()
def parser():
    return build_parser()


class TestGlobalFlags:
    def test_version_flag(self, parser):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        assert exc.value.code == 0

    def test_no_command_gives_none(self, parser):
        args = parser.parse_args([])
        assert args.command is None

    def test_verbose_flag(self, parser):
        args = parser.parse_args(["-v", "diff", "a.dxf", "b.dxf"])
        assert args.verbose is True

    def test_json_flag(self, parser):
        args = parser.parse_args(["--json", "diff", "a.dxf", "b.dxf"])
        assert args.json is True

    def test_defaults_verbose_false(self, parser):
        args = parser.parse_args(["diff", "a.dxf", "b.dxf"])
        assert args.verbose is False

    def test_defaults_json_false(self, parser):
        args = parser.parse_args(["diff", "a.dxf", "b.dxf"])
        assert args.json is False


class TestDiffCommand:
    def test_basic_diff(self, parser):
        args = parser.parse_args(["diff", "master.dxf", "revision.dxf"])
        assert args.command == "diff"
        assert args.master == "master.dxf"
        assert args.revision == "revision.dxf"

    def test_diff_with_output_dir(self, parser):
        args = parser.parse_args(["diff", "m.dxf", "r.dxf", "--output-dir", "/tmp/out"])
        assert args.output_dir == "/tmp/out"

    def test_diff_tolerance_default(self, parser):
        args = parser.parse_args(["diff", "m.dxf", "r.dxf"])
        assert args.tolerance == 1.0

    def test_diff_custom_tolerance(self, parser):
        args = parser.parse_args(["diff", "m.dxf", "r.dxf", "--tolerance", "0.5"])
        assert args.tolerance == 0.5

    def test_diff_missing_args(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["diff"])


class TestCompareAlias:
    def test_compare_is_parsed(self, parser):
        args = parser.parse_args(["compare", "m.dxf", "r.dxf"])
        assert args.command == "compare"
        assert args.master == "m.dxf"


class TestAlignCommand:
    def test_basic_align(self, parser):
        args = parser.parse_args(["align", "m.dxf", "r.dxf"])
        assert args.command == "align"
        assert args.confidence == 0.3
        assert args.max_residual == 5.0

    def test_align_custom_thresholds(self, parser):
        args = parser.parse_args(
            ["align", "m.dxf", "r.dxf", "--confidence", "0.8", "--max-residual", "2.0"]
        )
        assert args.confidence == 0.8
        assert args.max_residual == 2.0

    def test_align_control_points_flag(self, parser):
        args = parser.parse_args(
            ["align", "m.dxf", "r.dxf", "--control-points", "0,0:5,3", "100,0:105,3"]
        )
        assert args.control_points == ["0,0:5,3", "100,0:105,3"]

    def test_align_control_points_none_by_default(self, parser):
        args = parser.parse_args(["align", "m.dxf", "r.dxf"])
        assert args.control_points is None

    def test_diff_control_points_flag(self, parser):
        args = parser.parse_args(["diff", "m.dxf", "r.dxf", "--control-points", "0,0:5,3"])
        assert args.control_points == ["0,0:5,3"]


class TestDryRunCommand:
    def test_basic_dry_run(self, parser):
        args = parser.parse_args(["dry-run", "m.dxf", "r.dxf"])
        assert args.command == "dry-run"

    def test_dry_run_with_output_dir(self, parser):
        args = parser.parse_args(["dry-run", "m.dxf", "r.dxf", "--output-dir", "/out"])
        assert args.output_dir == "/out"


class TestApplyCommand:
    def test_apply_requires_output(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["apply", "m.dxf", "r.dxf"])

    def test_apply_with_output(self, parser):
        args = parser.parse_args(["apply", "m.dxf", "r.dxf", "--output", "out.dxf"])
        assert args.command == "apply"
        assert args.output == "out.dxf"
        assert args.approve_all is False

    def test_apply_approve_all(self, parser):
        args = parser.parse_args(
            ["apply", "m.dxf", "r.dxf", "--output", "out.dxf", "--approve-all"]
        )
        assert args.approve_all is True


class TestBundleCommand:
    def test_bundle_requires_output_dir(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["bundle", "m.dxf", "r.dxf"])

    def test_bundle_with_output_dir(self, parser):
        args = parser.parse_args(["bundle", "m.dxf", "r.dxf", "--output-dir", "/out"])
        assert args.command == "bundle"
        assert args.output_dir == "/out"
        assert args.approve_all is False


class TestExplainCommand:
    def test_basic_explain(self, parser):
        args = parser.parse_args(["explain", "m.dxf", "r.dxf"])
        assert args.command == "explain"
        assert args.master == "m.dxf"
        assert args.revision == "r.dxf"
