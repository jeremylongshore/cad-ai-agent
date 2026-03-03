#!/usr/bin/env bash
# Download externally-sourced DXF fixtures for e2e testing.
# Sources: jscad/sample-files (MIT), assimp (BSD-3), gdsestimating/dxf-parser (MIT)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$PROJECT_ROOT/tests/fixtures/dxf_zoo/sourced"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"

mkdir -p "$DEST"

JSCAD="https://raw.githubusercontent.com/jscad/sample-files/master/dxf"
ASSIMP="https://raw.githubusercontent.com/assimp/assimp/master/test/models/DXF"
GDS="https://raw.githubusercontent.com/gdsestimating/dxf-parser/master"

# name|url pairs
FILES="
jscad-2Dlines.dxf|${JSCAD}/autocad2017/2Dlines.dxf
jscad-2Dcircles.dxf|${JSCAD}/autocad2017/2Dcircles.dxf
jscad-2Dpolylines.dxf|${JSCAD}/autocad2017/2Dpolylines.dxf
jscad-2Drectangles.dxf|${JSCAD}/autocad2017/2Drectangles.dxf
jscad-2Darcs.dxf|${JSCAD}/autocad2017/2Darcs.dxf
jscad-2Dellipses.dxf|${JSCAD}/autocad2017/2Dellipses.dxf
jscad-2Dpoints.dxf|${JSCAD}/autocad2017/2Dpoints.dxf
jscad-3Dboxes.dxf|${JSCAD}/autocad2017/3Dboxes.dxf
jscad-3Dshapes.dxf|${JSCAD}/autocad2017/3Dshapes.dxf
jscad-emptyR12.dxf|${JSCAD}/autocad2017/emptyR12.dxf
jscad-empty2000.dxf|${JSCAD}/autocad2017/empty2000.dxf
jscad-floorplan.dxf|${JSCAD}/dxf-parser/floorplan.dxf
jscad-blocks1.dxf|${JSCAD}/dxf-parser/blocks1.dxf
jscad-blocks2.dxf|${JSCAD}/dxf-parser/blocks2.dxf
jscad-entities.dxf|${JSCAD}/dxf-parser/entities.dxf
jscad-lwpolylines.dxf|${JSCAD}/dxf-parser/lwpolylines.dxf
jscad-texts.dxf|${JSCAD}/dxf-parser/texts.dxf
jscad-layers.dxf|${JSCAD}/dxf-parser/layers.dxf
jscad-dimensions.dxf|${JSCAD}/dxf-parser/dimensions.dxf
jscad-polylines.dxf|${JSCAD}/dxf-parser/polylines.dxf
jscad-hatches.dxf|${JSCAD}/dxf-parser/hatches.dxf
jscad-CustomBlocks.dxf|${JSCAD}/ezdxf/CustomBlocks.dxf
jscad-Minimal_AC1009.dxf|${JSCAD}/ezdxf/Minimal_DXF_AC1009.dxf
jscad-small_r13.dxf|${JSCAD}/ezdxf/small_r13.dxf
jscad-no_layouts.dxf|${JSCAD}/ezdxf/no_layouts.dxf
jscad-square10x10.dxf|${JSCAD}/jscad/square10x10.dxf
jscad-circle10.dxf|${JSCAD}/jscad/circle10.dxf
jscad-3d-entities.dxf|${JSCAD}/bourke/3d-entities.dxf
assimp-PinkEggFromLW.dxf|${ASSIMP}/PinkEggFromLW.dxf
assimp-wuson.dxf|${ASSIMP}/wuson.dxf
gds-api-cw750-details.dxf|${GDS}/samples/data/api-cw750-details.dxf
gds-blocks.dxf|${GDS}/test/data/blocks.dxf
gds-mtext-test.dxf|${GDS}/test/data/mtext-test.dxf
gds-polylines.dxf|${GDS}/test/data/polylines.dxf
gds-extendeddata.dxf|${GDS}/test/data/extendeddata.dxf
"

DOWNLOADED=0
FAILED=0
SKIPPED=0

echo "==> Downloading DXF files into $DEST"

while IFS='|' read -r name url; do
  [[ -z "$name" ]] && continue
  dest_file="$DEST/$name"

  if [[ -f "$dest_file" ]]; then
    echo "  [skip] $name"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if curl -fsSL --retry 2 --max-time 30 -o "$dest_file" "$url" 2>/dev/null; then
    echo "  [ok]   $name"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    echo "  [FAIL] $name"
    rm -f "$dest_file"
    FAILED=$((FAILED + 1))
  fi
done <<< "$FILES"

echo ""
echo "==> Validating with ezdxf..."
VALID=0
INVALID=0

for f in "$DEST"/*.dxf; do
  [[ ! -f "$f" ]] && continue
  name=$(basename "$f")
  if $PYTHON -c "
import ezdxf, sys
try:
    doc = ezdxf.readfile(sys.argv[1])
    msp = doc.modelspace()
    n = len(list(msp))
    print(f'  [valid] {sys.argv[2]} — {n} entities, version {doc.dxfversion}')
except Exception as e:
    print(f'  [INVALID] {sys.argv[2]} — {e}')
    sys.exit(1)
" "$f" "$name" 2>&1; then
    VALID=$((VALID + 1))
  else
    echo "  Removing invalid file: $name"
    rm -f "$f"
    INVALID=$((INVALID + 1))
  fi
done

echo ""
TOTAL=$(ls "$DEST"/*.dxf 2>/dev/null | wc -l)
echo "==> Summary: downloaded=$DOWNLOADED, skipped=$SKIPPED, failed=$FAILED, valid=$VALID, invalid=$INVALID"
echo "    Total valid files: $TOTAL"
