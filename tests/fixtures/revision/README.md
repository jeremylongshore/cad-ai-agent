# Revision Test Fixtures

Test corpus proving the deterministic revision workflow is correct and stable.

Each fixture is a **master + revision DXF pair** that exercises the
convert → align → diff → dry-run → apply → verify pipeline.

## Directory Layout

```
revision/
  clean/                  Well-formed pairs — happy path (synthetic)
  clean_realworld/        Well-formed pair seeded from real DXF file

  nasty/                  Edge cases that must not crash or mis-align
    partial_revision/     Revision cloud covers only part of the drawing
    unit_mismatch/        Master in inches, revision in millimeters
    rotation_shift/       Revision rotated and/or shifted vs master
    block_attrib_changes/ Block INSERT attribute edits
    xrefs/                External references present in one or both files
    uncommon_entities/    Real DXF with 18 entity types (DIMENSION, SPLINE, MESH, etc.)
    real_columns/         Real column layout with MTEXT + polylines
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
| `uncommon_entities/` | Real ezdxf example with 18 entity types (DIMENSION, SPLINE, MESH, 3DSOLID, etc.) |
| `real_columns/` | Real column layout — MTEXT + LWPOLYLINE on single layer, tests content modification |

## Conventions

- Filenames: `master.dxf`, `revision.dxf`, `expected.json` per fixture directory
- DXF files are built programmatically by `tests/helpers/dxf_factory.py` or committed as static files
- Real-file-seeded fixtures include `SEED_LICENSE.md` with source attribution (MIT from ezdxf)
- Golden outputs (`expected.json`) are auto-generated with `UPDATE_GOLDENS=1` and checked in
- Each nasty fixture may also have an `expected_failure.json` if the correct behavior is rejection

## Adding a New Fixture

1. Create a subdirectory under `clean/` or `nasty/`
2. Add `master.dxf` and `revision.dxf`
3. Run the pipeline with `UPDATE_GOLDENS=1` to generate `expected.json`
4. Review the golden output, commit
5. The golden test harness (cad-wcn.4) will catch any future drift
