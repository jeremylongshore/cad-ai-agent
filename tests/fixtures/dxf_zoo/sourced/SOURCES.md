# Sourced DXF Fixtures — Attribution

These DXF files are sourced from open-source repositories for end-to-end testing.
They are **not** project-generated fixtures — they represent real-world CAD files
produced by various CAD software across multiple DXF versions.

## Sources

### jscad/sample-files (MIT License)
- **Repository**: https://github.com/jscad/sample-files
- **License**: MIT
- **Files**: `jscad-*.dxf`
- **Subdirectories used**: `dxf/autocad2017/`, `dxf/dxf-parser/`, `dxf/ezdxf/`, `dxf/jscad/`, `dxf/bourke/`
- **Content**: AutoCAD 2017 samples (2D/3D primitives), floor plans, block definitions,
  text entities, layers, dimensions, hatches, polylines, and minimal format samples
  across DXF versions AC1009 through AC1027.

### assimp/assimp (BSD 3-Clause License)
- **Repository**: https://github.com/assimp/assimp
- **License**: BSD 3-Clause ("Open Asset Import Library")
- **Files**: `assimp-*.dxf`
- **Content**: DXF test models from the Open Asset Import Library test suite.

### gdsestimating/dxf-parser (MIT License)
- **Repository**: https://github.com/gdsestimating/dxf-parser
- **License**: MIT
- **Files**: `gds-*.dxf`
- **Content**: Mechanical/architectural DXF samples including detailed curtain wall
  specifications, MTEXT, polylines, and extended data.

## Download

To refresh or re-download these fixtures:

```bash
bash scripts/download_sourced_fixtures.sh
```

The script downloads from raw GitHub URLs, validates each file with `ezdxf.readfile()`,
and removes any that fail validation.
