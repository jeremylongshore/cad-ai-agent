# Revision Test Fixtures

Test corpus proving the deterministic revision workflow is correct and stable.

Each fixture is a **master + revision DXF pair** that exercises the
convert → align → diff → dry-run → apply → verify pipeline.

## Directory Layout

```
revision/
  clean/              Well-formed pairs — happy path
    master.dxf        Original drawing
    revision.dxf      Revised drawing with known changes
    expected.json     Golden pipeline output (auto-generated, reviewed)

  nasty/              Edge cases that must not crash or mis-align
    partial_revision/     Revision cloud covers only part of the drawing
    unit_mismatch/        Master in inches, revision in millimeters (or vice versa)
    rotation_shift/       Revision is rotated and/or shifted vs master
    block_attrib_changes/ Block attribute edits (tag values, visibility)
    xrefs/                External references present in one or both files
```

## Taxonomy

### clean/

Straightforward structural changes that the pipeline must handle correctly:

- Moved column (INSERT repositioned)
- Modified wall (polyline vertices changed)
- Added embed (new INSERT block)

These produce a single golden output file (`expected.json`) that the test
harness compares against actual pipeline output.

### nasty/

Edge cases that stress alignment, coordinate mapping, and entity matching.
Each subdirectory contains its own master/revision pair and expected output.

| Subdirectory | What It Tests |
|---|---|
| `partial_revision/` | Revision extents cover only a region; entities outside must be ignored |
| `unit_mismatch/` | Drawing units differ between master and revision |
| `rotation_shift/` | Revision is geometrically transformed (rotation, translation, or both) |
| `block_attrib_changes/` | Block INSERT attributes changed (tag text, visibility flags) |
| `xrefs/` | One or both files contain external references that must not confuse alignment |

## Conventions

- Filenames: `master.dxf`, `revision.dxf`, `expected.json` per fixture directory
- DXF files are built programmatically by `tests/helpers/dxf_factory.py` or committed as static files
- Golden outputs (`expected.json`) are auto-generated with `UPDATE_GOLDENS=1` and checked in
- Each nasty fixture may also have an `expected_failure.json` if the correct behavior is rejection

## Adding a New Fixture

1. Create a subdirectory under `clean/` or `nasty/`
2. Add `master.dxf` and `revision.dxf`
3. Run the pipeline with `UPDATE_GOLDENS=1` to generate `expected.json`
4. Review the golden output, commit
5. The golden test harness (cad-wcn.4) will catch any future drift
