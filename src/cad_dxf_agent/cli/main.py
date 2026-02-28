"""CLI entry point for cad-revision — DXF comparison pipeline."""

from __future__ import annotations

import argparse
import logging
import sys

from .. import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. Standalone for testability."""
    parser = argparse.ArgumentParser(
        prog="cad-revision",
        description="Compare and apply revisions between DXF drawings.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    sub = parser.add_subparsers(dest="command")

    # --- diff ---
    p_diff = sub.add_parser("diff", help="Compare two DXF files and show changes")
    _add_input_args(p_diff)
    p_diff.add_argument("--output-dir", help="Directory for changelog and overlay files")
    p_diff.add_argument(
        "--tolerance", type=float, default=1.0, help="Coordinate tolerance (default: 1.0)"
    )

    # hidden alias: compare
    p_compare = sub.add_parser("compare")
    _add_input_args(p_compare)
    p_compare.add_argument("--output-dir", help="Directory for changelog and overlay files")
    p_compare.add_argument(
        "--tolerance", type=float, default=1.0, help="Coordinate tolerance (default: 1.0)"
    )

    # --- align ---
    p_align = sub.add_parser("align", help="Align two drawings and show transform")
    _add_input_args(p_align)
    p_align.add_argument(
        "--confidence", type=float, default=0.3, help="Min confidence threshold (default: 0.3)"
    )
    p_align.add_argument(
        "--max-residual", type=float, default=5.0, help="Max RMS residual (default: 5.0)"
    )

    # --- dry-run ---
    p_dryrun = sub.add_parser("dry-run", help="Show proposed ops without applying")
    _add_input_args(p_dryrun)
    p_dryrun.add_argument("--output-dir", help="Directory for overlay and changelog")
    p_dryrun.add_argument(
        "--confidence", type=float, default=0.3, help="Min confidence threshold (default: 0.3)"
    )

    # --- apply ---
    p_apply = sub.add_parser("apply", help="Apply revision changes to master")
    _add_input_args(p_apply)
    p_apply.add_argument("--output", required=True, help="Output DXF path (required)")
    p_apply.add_argument("--approve-all", action="store_true", help="Auto-approve all pending ops")

    # --- bundle ---
    p_bundle = sub.add_parser("bundle", help="Full pipeline: compare, apply, export bundle")
    _add_input_args(p_bundle)
    p_bundle.add_argument("--output-dir", required=True, help="Bundle output directory (required)")
    p_bundle.add_argument("--approve-all", action="store_true", help="Auto-approve all pending ops")

    # --- explain ---
    p_explain = sub.add_parser("explain", help="Generate human-readable changelog")
    _add_input_args(p_explain)

    return parser


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared master/revision positional arguments."""
    parser.add_argument("master", help="Path to master (original) DXF file")
    parser.add_argument("revision", help="Path to revision (modified) DXF file")


def main(argv: list[str] | None = None) -> int:
    """Parse args, dispatch to command handler, return exit code.

    Exit codes: 0 = no changes, 1 = changes found, 2 = error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # Treat "compare" as alias for "diff"
    if args.command == "compare":
        args.command = "diff"

    from . import commands

    dispatch = {
        "diff": commands.cmd_diff,
        "align": commands.cmd_align,
        "dry-run": commands.cmd_dry_run,
        "apply": commands.cmd_apply,
        "bundle": commands.cmd_bundle,
        "explain": commands.cmd_explain,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2

    try:
        return handler(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
