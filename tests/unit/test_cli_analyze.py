"""Tests for the cad-analyze headless analysis CLI.

Every subcommand must run on a real DXF with no LLM/API key, exit cleanly, and
emit valid JSON under --json (the contract the Claude Code skill depends on).
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from cad_dxf_agent.cli.analyze import build_parser, main
from tests.helpers.dxf_factory import create_structural_drawing


def _run(argv: list[str]) -> tuple[int, str]:
    """Run cad-analyze, capturing exit code + stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


@pytest.fixture
def dxf(tmp_path):
    return str(create_structural_drawing(tmp_path))


class TestAnalyzeJsonOutput:
    @pytest.mark.parametrize("cmd", ["health", "takeoff", "summary", "rfi", "zones"])
    def test_subcommand_emits_valid_json_and_exits_zero(self, cmd, dxf):
        code, out = _run([cmd, dxf, "--json"])
        assert code == 0
        parsed = json.loads(out)  # raises if not valid JSON
        assert isinstance(parsed, dict)

    def test_compliance_emits_valid_json(self, dxf):
        code, out = _run(["compliance", dxf, "--json"])
        assert code in (0, 1)  # 1 = violations present, still valid output
        data = json.loads(out)
        assert data["profile_name"]
        assert "findings" in data

    def test_compliance_profile_flag_is_honored(self, dxf):
        _, out = _run(["compliance", dxf, "--profile", "ibc-2021", "--json"])
        data = json.loads(out)
        assert "ibc" in data["profile_name"].lower()

    def test_zones_tolerance_flag_accepted(self, dxf):
        code, out = _run(["zones", dxf, "--tolerance", "1.0", "--json"])
        assert code == 0
        assert isinstance(json.loads(out), dict)


class TestAnalyzeTextOutput:
    def test_text_mode_prints_title_and_fields(self, dxf):
        code, out = _run(["health", dxf])
        assert code == 0
        assert out.startswith("# Drawing Health")
        assert "score" in out


class TestAnalyzeErrors:
    def test_missing_file_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            _run(["health", "/no/such/file.dxf", "--json"])
        assert exc.value.code == 2

    def test_no_subcommand_errors(self):
        # argparse with required subparser exits 2 on no command
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args([])
        assert exc.value.code == 2

    def test_version_flag(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--version"])
        assert exc.value.code == 0
