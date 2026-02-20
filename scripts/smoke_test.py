#!/usr/bin/env python3
"""End-to-end smoke test — runs the full pipeline without an LLM API key.

Usage:
    python scripts/smoke_test.py

This script:
  1. Creates a sample DXF programmatically
  2. Loads it into a DrawingContext
  3. Runs the mock planner
  4. Validates the proposed operations
  5. Applies the operations via EditEngine
  6. Inserts an AI revision note
  7. Saves the output DXF
  8. Prints a summary
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Ensure src is importable when running as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ezdxf

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.preview_model import PreviewModel
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig


def create_sample_dxf(path: Path) -> Path:
    """Create a minimal sample DXF with V1-supported entities."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)
    doc.layers.add("REVISION", color=7)

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_lwpolyline(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp.add_text(
        "Column C-4",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )
    msp.add_mtext(
        "Footing detail",
        dxfattribs={"layer": "NOTES", "insert": (20, 20), "char_height": 2.0},
    )
    msp.add_text(
        "PROJECT TITLE",
        dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -20)},
    )

    block = doc.blocks.new("COLUMN_MARK")
    block.add_circle((0, 0), radius=2)
    msp.add_blockref("COLUMN_MARK", insert=(25, 25), dxfattribs={"layer": "STRUCTURAL"})

    doc.saveas(str(path))
    return path


def main() -> int:
    print("=" * 60)
    print("cad-dxf-agent SMOKE TEST (mock planner, no API key)")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="cad_smoke_") as tmpdir:
        tmp = Path(tmpdir)
        input_dxf = tmp / "input.dxf"
        output_dxf = tmp / "output_edited.dxf"

        # Step 1: Create sample DXF
        print("\n[1/7] Creating sample DXF...")
        create_sample_dxf(input_dxf)
        print(f"  Created: {input_dxf}")

        # Step 2: Load into DrawingContext
        print("\n[2/7] Loading DXF into DrawingContext...")
        context = load_dxf(input_dxf)
        print(f"  Entities: {context.entity_count}")
        print(f"  Layers: {[l.name for l in context.layers]}")
        print(f"  Protected: {context.get_protected_layers()}")
        print(f"  Blocks: {context.blocks}")

        # Step 3: Run mock planner
        print("\n[3/7] Running mock planner...")
        drawing_ctx = build_planner_context(context)
        changeset = run_planner("Move the column east by 2 feet", drawing_ctx)
        print(f"  Operations: {changeset.op_count}")
        for op in changeset.operations:
            print(f"    - {op.op_type.value}: handle={op.target_handle} params={op.params}")

        # Step 4: Validate
        print("\n[4/7] Validating operations...")
        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        print(f"  Valid: {validation.valid}")
        for b in validation.blockers:
            print(f"  BLOCKER: {b.message}")
        for w in validation.warnings:
            print(f"  WARNING: {w.message}")

        if not validation.valid:
            print("\n  SMOKE TEST FAILED: validation blocked operations")
            return 1

        # Step 5: Preview
        print("\n[5/7] Building preview...")
        preview = PreviewModel(changeset, context, validation)
        print(preview.summary)

        # Step 6: Apply
        print("\n[6/7] Applying operations...")
        engine = EditEngine(input_dxf)
        results = engine.apply_changeset(changeset)
        engine.save(output_dxf)
        for r in results:
            status = "OK" if r.success else "FAIL"
            print(f"  [{status}] {r.description}")

        # Step 7: Insert revision note
        print("\n[7/7] Inserting AI revision note...")
        rev_config = RevisionNoteConfig(revision_number=8)
        note_text = insert_revision_note(output_dxf, output_dxf, results, rev_config)
        print(f"  Note: {note_text}")
        print(f"  Layer: {rev_config.layer_name}")

        # Verify output
        print("\n" + "=" * 60)
        print("SMOKE TEST PASSED")
        print(f"  Input:  {input_dxf}")
        print(f"  Output: {output_dxf}")
        print(f"  Original untouched: {input_dxf.exists()}")

        # Verify output is valid DXF
        verify_doc = ezdxf.readfile(str(output_dxf))
        verify_msp = verify_doc.modelspace()
        output_entities = list(verify_msp)
        print(f"  Output entities: {len(output_entities)}")
        print(f"  AI_REV_NOTES layer exists: {'AI_REV_NOTES' in verify_doc.layers}")
        print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
