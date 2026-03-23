#!/usr/bin/env bash
# ============================================================================
# Architectural Drift Detection Gate
# ============================================================================
# Scans the codebase for violations of key architectural invariants.
# Runs as the first CI job — all other jobs depend on this passing.
#
# Checks:
#   1. No forbidden framework imports (langchain, crewai, autogen, llamaindex)
#   2. No raw DXF mutation outside the approved modules
#   3. Protected layer dual-enforcement (validators.py + tool_executor.py)
#   4. No .env files tracked by git
#
# Exit 0 on success, exit 1 on any violation.
# ============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VIOLATIONS=0

red()    { printf '\033[0;31m%s\033[0m\n' "$1"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$1"; }
header() { printf '\n=== %s ===\n' "$1"; }

# Helper: filter grep output, keeping only lines from unapproved files.
# Reads from stdin, prints unapproved hits to stdout.
filter_approved() {
    while IFS= read -r line; do
        local file_path
        file_path=$(echo "$line" | cut -d: -f1)
        local relative="${file_path#"$REPO_ROOT"/}"
        local is_approved=0
        for approved in "${APPROVED_MUTATION_FILES[@]}"; do
            if [[ "$relative" == "$approved" ]]; then
                is_approved=1
                break
            fi
        done
        if [[ $is_approved -eq 0 ]]; then
            echo "$line"
        fi
    done
}

# --------------------------------------------------------------------------
# 1. No forbidden framework imports in src/
# --------------------------------------------------------------------------
header "Check 1: No forbidden framework imports"

FORBIDDEN_FRAMEWORKS="langchain|crewai|autogen|llamaindex|llama_index"
if grep -rn --include='*.py' -E "^(import |from )(${FORBIDDEN_FRAMEWORKS})" "$REPO_ROOT/src/"; then
    red "FAIL: Forbidden framework imports found in src/."
    red "      This project uses Vertex AI / ADK only — no langchain, crewai, autogen, or llamaindex."
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: No forbidden framework imports."
fi

# --------------------------------------------------------------------------
# 2. No raw DXF mutation outside approved modules
# --------------------------------------------------------------------------
header "Check 2: No raw DXF mutation outside approved modules"

# Approved files for DXF write operations (msp.add_*, doc.saveas, entity.dxf.X = ...)
APPROVED_MUTATION_FILES=(
    "src/cad_dxf_agent/core/edit_engine.py"
    "src/cad_dxf_agent/core/dxf_reader.py"
    "src/cad_dxf_agent/core/dxf_writer.py"
    "src/cad_dxf_agent/core/revision_notes.py"
    "src/cad_dxf_agent/core/converter.py"
    "src/cad_dxf_agent/core/comparison/applier.py"
    "src/cad_dxf_agent/core/comparison/diff_overlay.py"
    "src/cad_dxf_agent/core/comparison/bundle.py"
    "src/cad_dxf_agent/cli/commands.py"
)

DXF_MUTATION_FOUND=0

# 2a. Check for msp.add_* calls (entity creation)
HITS=$(grep -rn --include='*.py' -E 'msp\.add_' "$REPO_ROOT/src/" | filter_approved || true)
if [[ -n "$HITS" ]]; then
    red "FAIL: DXF entity creation (msp.add_*) found outside approved modules:"
    echo "$HITS"
    DXF_MUTATION_FOUND=1
fi

# 2b. Check for .saveas() calls (file saving)
HITS=$(grep -rn --include='*.py' -E '\.saveas\(' "$REPO_ROOT/src/" | filter_approved || true)
if [[ -n "$HITS" ]]; then
    red "FAIL: DXF save operations found outside approved modules:"
    echo "$HITS"
    DXF_MUTATION_FOUND=1
fi

# 2c. Check for entity.dxf.X = ... (attribute mutation via assignment)
#     Filter out comparison operators (==, !=) which are reads, not writes.
HITS=$(grep -rn --include='*.py' -E 'entity\.dxf\.\w+\s*=[^=]' "$REPO_ROOT/src/" | filter_approved || true)
if [[ -n "$HITS" ]]; then
    red "FAIL: DXF entity attribute mutation found outside approved modules:"
    echo "$HITS"
    DXF_MUTATION_FOUND=1
fi

if [[ $DXF_MUTATION_FOUND -eq 1 ]]; then
    red "      DXF mutations must be contained in: edit_engine, dxf_reader, dxf_writer, revision_notes,"
    red "      converter, comparison/applier, comparison/diff_overlay, comparison/bundle, cli/commands."
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: No DXF mutations outside approved modules."
fi

# --------------------------------------------------------------------------
# 3. Protected layer dual-enforcement
# --------------------------------------------------------------------------
header "Check 3: Protected layer dual-enforcement"

PROTECTED_LAYERS_RE='TITLE.*TITLEBLOCK.*SEAL.*REVISION'
DUAL_ENFORCEMENT_OK=1

# Check validators.py has protected layer reference
if ! grep -q 'protected_layers' "$REPO_ROOT/src/cad_dxf_agent/core/validators.py"; then
    red "FAIL: src/cad_dxf_agent/core/validators.py does not enforce protected layers."
    DUAL_ENFORCEMENT_OK=0
fi

# Check tool_executor.py has protected layer reference
if ! grep -q 'protected' "$REPO_ROOT/src/cad_dxf_agent/llm/tool_executor.py"; then
    red "FAIL: src/cad_dxf_agent/llm/tool_executor.py does not enforce protected layers."
    DUAL_ENFORCEMENT_OK=0
fi

# Verify the canonical list exists in config_schema.py (source of truth)
if ! grep -qE "$PROTECTED_LAYERS_RE" "$REPO_ROOT/src/cad_dxf_agent/models/config_schema.py"; then
    red "FAIL: Canonical protected layer list (TITLE, TITLEBLOCK, SEAL, REVISION) missing from config_schema.py."
    DUAL_ENFORCEMENT_OK=0
fi

if [[ $DUAL_ENFORCEMENT_OK -eq 0 ]]; then
    red "      Protected layers must be enforced in BOTH validators.py AND tool_executor.py."
    red "      Canonical list defined in models/config_schema.py."
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: Protected layer dual-enforcement verified."
fi

# --------------------------------------------------------------------------
# 4. No .env files committed
# --------------------------------------------------------------------------
header "Check 4: No .env files committed"

# Check for tracked .env files (excluding .env.example which is expected)
TRACKED_ENV=$(cd "$REPO_ROOT" && git ls-files '*.env' '.env*' 'web/.env*' | grep -v '\.env\.example$' || true)
if [[ -n "$TRACKED_ENV" ]]; then
    red "FAIL: .env files are tracked by git:"
    echo "$TRACKED_ENV"
    red "      Remove them with: git rm --cached <file>"
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: No .env files committed (only .env.example, which is expected)."
fi

# --------------------------------------------------------------------------
# 5. No google.adk imports outside approved ADK module
# --------------------------------------------------------------------------
header "Check 5: No google.adk imports outside approved module"

ADK_IMPORT_HITS=$(grep -rn --include='*.py' -E '^(import |from )google\.adk' "$REPO_ROOT/src/" | grep -v 'src/cad_dxf_agent/adk/' || true)
if [[ -n "$ADK_IMPORT_HITS" ]]; then
    red "FAIL: google.adk imports found outside src/cad_dxf_agent/adk/:"
    echo "$ADK_IMPORT_HITS"
    red "      ADK imports must only appear in the adk/ module (when it exists)."
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: No google.adk imports outside approved module."
fi

# --------------------------------------------------------------------------
# 6. Gateway must not import google.adk (bobs-brain R3: gateway = pure proxy)
# --------------------------------------------------------------------------
header "Check 6: Gateway (web/backend/main.py) does not import google.adk"

if grep -qn -E '^(import |from )google\.adk' "$REPO_ROOT/web/backend/main.py" 2>/dev/null; then
    red "FAIL: web/backend/main.py imports google.adk."
    red "      The gateway must be a pure proxy — no ADK dependency."
    VIOLATIONS=$((VIOLATIONS + 1))
else
    green "PASS: Gateway does not import google.adk."
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
if [[ $VIOLATIONS -gt 0 ]]; then
    red "DRIFT DETECTED: $VIOLATIONS violation(s) found. Fix them before merging."
    exit 1
else
    green "ALL CLEAR: No architectural drift detected."
    exit 0
fi
