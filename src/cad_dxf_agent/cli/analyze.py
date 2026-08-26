"""cad-analyze — headless deterministic drawing analysis CLI.

Runs the no-LLM analysis capabilities against a DXF and prints a human-readable
report or, with ``--json``, the structured report model. None of these
capabilities call an LLM or require an API key — they are pure deterministic
extractors, which makes this CLI the stable contract the Claude Code skill drives.

Subcommands:
  compliance  ADA/IBC/custom rule validation
  health      drawing quality / health report
  takeoff     automated quantity takeoff
  summary     plain-English drawing summary
  rfi         RFIs generated from detected ambiguities
  zones       closed-loop room/zone detection
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from pathlib import Path

from ezdxf.lldxf.const import DXFStructureError

from .. import __version__
from ..core.compliance_rules import check_compliance
from ..core.drawing_summarizer import summarize_drawing
from ..core.dxf_reader import load_dxf
from ..core.health_checker import check_drawing_health
from ..core.rfi_generator import generate_rfi
from ..core.takeoff_engine import generate_takeoff
from ..core.zone_detector import detect_zones


def _load_context(path: str):
    """Load a DXF into a DrawingContext, or exit(2) with a clear message."""
    p = Path(path)
    if not p.exists():
        print(f"cad-analyze: file not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        return load_dxf(p)
    except (OSError, DXFStructureError) as exc:
        print(f"cad-analyze: unable to read DXF {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _emit(report, *, title: str, as_json: bool) -> None:
    """Print the report as indented JSON (--json) or a readable text summary."""
    if as_json:
        print(report.model_dump_json(indent=2))
        return
    data = report.model_dump()
    print(f"# {title}")
    for key, value in data.items():
        if isinstance(value, list):
            print(f"{key} ({len(value)}):")
            for item in value[:25]:
                print(f"  - {item}")
        elif isinstance(value, dict):
            print(f"{key}: {{{len(value)} keys}}")
        else:
            print(f"{key}: {value}")


def cmd_compliance(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    zones = detect_zones(ctx)
    report = check_compliance(ctx, profile=args.profile, zones=zones)
    _emit(report, title=f"Compliance ({args.profile})", as_json=args.json)
    # Non-zero exit when violations are present, so callers/CI can gate on it.
    return 1 if report.violation_count > 0 else 0


def cmd_health(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    report = check_drawing_health(ctx)
    _emit(report, title="Drawing Health", as_json=args.json)
    return 0


def cmd_takeoff(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    zones = detect_zones(ctx)
    report = generate_takeoff(ctx, zones=zones)
    _emit(report, title="Quantity Takeoff", as_json=args.json)
    return 0


def cmd_summary(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    zones = detect_zones(ctx)
    report = summarize_drawing(ctx, zones=zones)
    _emit(report, title="Drawing Summary", as_json=args.json)
    return 0


def cmd_rfi(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    zones = detect_zones(ctx)
    report = generate_rfi(ctx, zones=zones)
    _emit(report, title="RFI", as_json=args.json)
    return 0


def cmd_zones(args: Namespace) -> int:
    ctx = _load_context(args.dxf)
    report = detect_zones(ctx, tolerance=args.tolerance)
    _emit(report, title="Zone Detection", as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cad-analyze",
        description="Headless deterministic DXF analysis — no LLM or API key required.",
    )
    parser.add_argument("--version", action="version", version=f"cad-analyze {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("dxf", help="Path to the DXF file to analyze")
        sp.add_argument("--json", action="store_true", help="Emit the structured report as JSON")
        sp.set_defaults(handler=handler)
        return sp

    _add("health", cmd_health, "Drawing quality / health report")
    _add("takeoff", cmd_takeoff, "Automated quantity takeoff")
    _add("summary", cmd_summary, "Plain-English drawing summary")
    _add("rfi", cmd_rfi, "Generate RFIs from detected ambiguities")

    p_comp = _add("compliance", cmd_compliance, "ADA/IBC/custom compliance check")
    p_comp.add_argument(
        "--profile",
        default="ada",
        help="Compliance profile (default: ada; e.g. ibc-2021, residential)",
    )

    p_zones = _add("zones", cmd_zones, "Closed-loop room/zone detection with area calc")
    p_zones.add_argument(
        "--tolerance", type=float, default=0.5, help="Loop-closing tolerance (default: 0.5)"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``cad-analyze`` console script."""
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
