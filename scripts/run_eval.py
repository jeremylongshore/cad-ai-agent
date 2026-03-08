#!/usr/bin/env python3
"""Capability scorecard evaluation runner.

Usage:
    python scripts/run_eval.py                    # Run all scorecard entries (mock)
    python scripts/run_eval.py --family qna       # Run only qna entries
    python scripts/run_eval.py --output results/  # Save JSON results

Loads scorecard entries from tests/eval/scorecard_entries.json,
runs each through the intent router + response pipeline (mock provider),
and produces a ScorecardSummary with per-entry results.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_entries(path: Path, family: str | None = None) -> list[dict]:
    """Load scorecard entries from JSON file."""
    data = json.loads(path.read_text())
    entries = data if isinstance(data, list) else data.get("entries", [])
    if family:
        entries = [e for e in entries if e.get("task_family") == family]
    return entries


def evaluate_entry(entry: dict) -> dict:
    """Evaluate a single scorecard entry against the router."""
    from cad_dxf_agent.llm.intent_router import IntentRouter
    from cad_dxf_agent.models.scorecard_schema import ScoreVerdict

    start = time.monotonic()
    result = {
        "entry_id": entry["entry_id"],
        "verdict": ScoreVerdict.PASS,
        "score_intent": 0.0,
        "score_safety": 1.0,
        "score_quality": 0.0,
        "score_composite": 0.0,
        "latency_ms": 0,
        "failure_reason": None,
        "actual_task_family": None,
        "actual_response_type": None,
        "actual_op_count": 0,
        "actual_evidence_count": 0,
    }

    try:
        router = IntentRouter()
        intent = router.classify(entry["prompt"])
        result["actual_task_family"] = intent.family.value

        # Score: intent classification
        if intent.family.value == entry["task_family"]:
            result["score_intent"] = 1.0
        else:
            result["score_intent"] = 0.0
            result["verdict"] = ScoreVerdict.FAIL
            result["failure_reason"] = (
                f"Expected family '{entry['task_family']}', "
                f"got '{intent.family.value}'"
            )

        # Score: safety (always 1.0 for router-only eval)
        result["score_safety"] = 1.0

        # Score: quality (1.0 if intent matched, 0.0 otherwise)
        result["score_quality"] = 1.0 if result["score_intent"] == 1.0 else 0.0

        # Composite: weighted average
        result["score_composite"] = (
            result["score_intent"] * 0.4
            + result["score_safety"] * 0.3
            + result["score_quality"] * 0.3
        )

    except Exception as e:
        result["verdict"] = ScoreVerdict.ERROR
        result["failure_reason"] = str(e)

    elapsed = time.monotonic() - start
    result["latency_ms"] = int(elapsed * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description="Run capability scorecard")
    parser.add_argument(
        "--entries",
        default=str(PROJECT_ROOT / "tests" / "eval" / "scorecard_entries.json"),
        help="Path to scorecard entries JSON",
    )
    parser.add_argument("--family", help="Filter to one task family")
    parser.add_argument("--output", help="Directory to save results JSON")
    args = parser.parse_args()

    entries_path = Path(args.entries)
    if not entries_path.exists():
        print(f"ERROR: {entries_path} not found", file=sys.stderr)
        sys.exit(1)

    entries = load_entries(entries_path, args.family)
    print(f"Running {len(entries)} scorecard entries...")

    from cad_dxf_agent.models.scorecard_schema import (
        ScorecardResult,
        ScorecardSummary,
    )

    summary = ScorecardSummary()
    for entry in entries:
        raw = evaluate_entry(entry)
        summary.results.append(ScorecardResult(**raw))
        verdict = raw["verdict"]
        eid = raw["entry_id"]
        print(f"  {verdict.upper():5s}  {eid}")

    summary.compute()

    print(f"\n{'='*50}")
    print(f"Total: {summary.total_entries}")
    print(f"Passed: {summary.passed}")
    print(f"Failed: {summary.failed}")
    print(f"Errors: {summary.errors}")
    print(f"Pass rate: {summary.pass_rate:.1%}")
    print(f"Mean composite: {summary.mean_composite:.3f}")
    if summary.safety_violations:
        print(f"SAFETY VIOLATIONS: {summary.safety_violations}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"scorecard-{ts}.json"
        out_path.write_text(
            json.dumps(summary.model_dump(), indent=2, default=str)
        )
        print(f"Results saved to {out_path}")

    sys.exit(0 if summary.failed == 0 and summary.errors == 0 else 1)


if __name__ == "__main__":
    main()
