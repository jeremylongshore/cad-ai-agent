#!/usr/bin/env bash
# Download DXF fixtures from public MIT-licensed repos for E2E testing.
# See tests/fixtures/e2e_sourced/SOURCES.md for license attribution.
#
# Usage: bash scripts/download_e2e_fixtures.sh
set -euo pipefail

# Use .venv python if available (has ezdxf), otherwise system python
PYTHON="${VIRTUAL_ENV:-$(dirname "$0")/../.venv}/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

DEST="tests/fixtures/e2e_sourced"
mkdir -p "$DEST"

# ── Source definitions ───────────────────────────────────────────────
# Format: local_name|repo_owner/repo_name|path_in_repo
FILES=(
  "jscad-texts.dxf|jscad/sample-files|dxf/dxf-parser/texts.dxf"
  "jscad-blocks1.dxf|jscad/sample-files|dxf/dxf-parser/blocks1.dxf"
  "jscad-blocks2.dxf|jscad/sample-files|dxf/dxf-parser/blocks2.dxf"
  "jscad-floorplan.dxf|jscad/sample-files|dxf/dxf-parser/floorplan.dxf"
  "jscad-CustomBlocks.dxf|jscad/sample-files|dxf/ezdxf/CustomBlocks.dxf"
  "gds-mtext-test.dxf|gdsestimating/dxf-parser|test/data/mtext-test.dxf"
  "gds-blocks.dxf|gdsestimating/dxf-parser|test/data/blocks.dxf"
  "gds-api-cw750.dxf|gdsestimating/dxf-parser|samples/data/api-cw750-details.dxf"
)

OK=0
SKIP=0
FAIL=0

for entry in "${FILES[@]}"; do
  IFS='|' read -r local_name repo path <<< "$entry"
  target="$DEST/$local_name"

  if [[ -f "$target" ]]; then
    echo "SKIP  $local_name (already present)"
    SKIP=$((SKIP + 1))
    continue
  fi

  url="https://raw.githubusercontent.com/$repo/main/$path"
  echo -n "GET   $local_name ... "

  # Try main branch, then master
  if curl -fsSL -o "$target" "$url" 2>/dev/null; then
    :
  else
    url="https://raw.githubusercontent.com/$repo/master/$path"
    if ! curl -fsSL -o "$target" "$url" 2>/dev/null; then
      echo "FAIL (not found on main or master)"
      FAIL=$((FAIL + 1))
      rm -f "$target"
      continue
    fi
  fi

  # Validate with ezdxf
  if "$PYTHON" -c "import ezdxf; ezdxf.readfile('$target')" 2>/dev/null; then
    echo "OK"
    OK=$((OK + 1))
  else
    echo "FAIL (ezdxf cannot read)"
    rm -f "$target"
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "Done: $OK downloaded, $SKIP skipped, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1
