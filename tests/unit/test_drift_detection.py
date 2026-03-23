"""Tests for architectural drift detection (scripts/ci/check_nodrift.sh).

The test suite has two layers:

1. Script-level integration tests — run the real bash script against the
   actual repo tree via subprocess.  ``test_clean_repo_passes`` is the
   primary gate: it confirms zero violations on the current working tree.

2. Pattern-unit tests — verify the exact regexes the script uses so that
   regressions in the patterns are caught without a full shell round-trip.
   These are fast, hermetic, and cover both positive (violation detected)
   and negative (approved code not flagged) cases.

Note on subprocess injection: the script resolves REPO_ROOT from its own
``$(dirname "$0")`` location, so it always scans the actual repo tree
regardless of the ``cwd`` passed to subprocess.run.  We therefore do not
attempt to inject temporary violations into a fake tree; instead the
pattern tests cover the detection logic, and the clean-repo test proves
the script runs correctly end-to-end.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_nodrift.sh"

# ---------------------------------------------------------------------------
# Compiled patterns — mirror what check_nodrift.sh uses
# ---------------------------------------------------------------------------

# Check 1
_FORBIDDEN_FRAMEWORK_RE = re.compile(
    r"^(import |from )(langchain|crewai|autogen|llamaindex|llama_index)",
    re.MULTILINE,
)

# Check 2
_MSP_ADD_RE = re.compile(r"msp\.add_")
_SAVEAS_RE = re.compile(r"\.saveas\(")
_ENTITY_ATTR_WRITE_RE = re.compile(r"entity\.dxf\.\w+\s*=[^=]")

# Check 5 & 6
_ADK_IMPORT_RE = re.compile(r"^(import |from )google\.adk", re.MULTILINE)

# ---------------------------------------------------------------------------
# Script-level tests
# ---------------------------------------------------------------------------


class TestScriptExists:
    """Basic sanity checks that the script is present and accessible."""

    def test_script_exists(self) -> None:
        """The drift detection script is present in the repo."""
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_script_starts_with_bash_shebang(self) -> None:
        """The script has a recognisable shell shebang on the first line."""
        first_line = SCRIPT.read_text().splitlines()[0]
        assert first_line.startswith("#!/"), f"Unexpected first line: {first_line!r}"
        assert "bash" in first_line or "env" in first_line


class TestCleanRepoPasses:
    """The script must exit 0 on the current unmodified repository."""

    def test_clean_repo_passes(self) -> None:
        """Running the script on the actual repo exits 0 (no violations)."""
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        assert result.returncode == 0, (
            "Drift detected in the repo — fix violations before merging.\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

    def test_clean_repo_output_contains_all_check_headers(self) -> None:
        """Every check emits its header and a PASS line when the repo is clean."""
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        assert result.returncode == 0
        for check_number in range(1, 7):
            assert f"Check {check_number}" in result.stdout, (
                f"Check {check_number} header missing from script output"
            )
        assert "ALL CLEAR" in result.stdout

    def test_clean_repo_has_no_pass_failures(self) -> None:
        """The word FAIL does not appear in the output on a clean run."""
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        assert "FAIL:" not in result.stdout, (
            f"Unexpected FAIL in clean-repo output:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# Check 1: Forbidden framework imports
# ---------------------------------------------------------------------------


class TestCheck1ForbiddenImports:
    """Regex used by Check 1 correctly matches and rejects the right lines."""

    @pytest.mark.parametrize(
        "bad_line",
        [
            "from langchain import chains",
            "import langchain",
            "from crewai import Agent",
            "import crewai",
            "from autogen import AssistantAgent",
            "import autogen",
            "from llamaindex import VectorIndex",
            "import llamaindex",
            "from llama_index.core import Document",
            "import llama_index",
        ],
    )
    def test_forbidden_import_pattern_matches(self, bad_line: str) -> None:
        """Pattern flags every top-level import of a forbidden framework."""
        assert _FORBIDDEN_FRAMEWORK_RE.search(bad_line), (
            f"Pattern should have matched: {bad_line!r}"
        )

    @pytest.mark.parametrize(
        "good_line",
        [
            "from vertexai import generative_models",
            "import google.cloud.aiplatform",
            "from google.adk import Agent",  # ADK is caught by check 5, not check 1
            "import google.generativeai",
            "# from langchain import chains",  # comment — no match expected
            "    from langchain import chains",  # indented — regex anchors to ^ with MULTILINE
        ],
    )
    def test_approved_import_not_flagged(self, good_line: str) -> None:
        """Lines that are not top-level forbidden imports do not match."""
        assert not _FORBIDDEN_FRAMEWORK_RE.search(good_line), (
            f"Pattern should NOT have matched: {good_line!r}"
        )

    def test_check1_passes_on_real_src(self) -> None:
        """No forbidden framework imports exist anywhere in src/."""
        violations: list[str] = []
        for py_file in (REPO_ROOT / "src").rglob("*.py"):
            content = py_file.read_text(errors="replace")
            if _FORBIDDEN_FRAMEWORK_RE.search(content):
                violations.append(str(py_file.relative_to(REPO_ROOT)))
        assert violations == [], "Forbidden framework imports found in src/:\n" + "\n".join(
            violations
        )


# ---------------------------------------------------------------------------
# Check 2: DXF mutation confined to approved modules
# ---------------------------------------------------------------------------

APPROVED_MUTATION_FILES: frozenset[str] = frozenset(
    [
        "src/cad_dxf_agent/core/edit_engine.py",
        "src/cad_dxf_agent/core/dxf_reader.py",
        "src/cad_dxf_agent/core/dxf_writer.py",
        "src/cad_dxf_agent/core/revision_notes.py",
        "src/cad_dxf_agent/core/converter.py",
        "src/cad_dxf_agent/core/comparison/applier.py",
        "src/cad_dxf_agent/core/comparison/diff_overlay.py",
        "src/cad_dxf_agent/core/comparison/bundle.py",
        "src/cad_dxf_agent/cli/commands.py",
    ]
)


class TestCheck2DxfMutation:
    """Check 2 verifies DXF mutations do not appear outside approved files."""

    def test_approved_files_list_contains_edit_engine(self) -> None:
        """edit_engine.py is always in the approved mutation file list."""
        assert "src/cad_dxf_agent/core/edit_engine.py" in APPROVED_MUTATION_FILES

    # --- msp.add_* ---

    @pytest.mark.parametrize(
        "line",
        [
            "msp.add_line((0, 0), (10, 0))",
            "msp.add_circle(center=(0, 0), radius=5)",
            "msp.add_lwpolyline(points)",
            "msp.add_text('hello')",
        ],
    )
    def test_msp_add_pattern_matches(self, line: str) -> None:
        """msp.add_* pattern catches entity-creation calls."""
        assert _MSP_ADD_RE.search(line), f"Pattern should match: {line!r}"

    def test_msp_add_not_in_unapproved_files(self) -> None:
        """No unapproved Python file contains a msp.add_* call."""
        violations = _find_pattern_outside_approved(_MSP_ADD_RE)
        assert violations == [], "msp.add_* found outside approved modules:\n" + "\n".join(
            violations
        )

    # --- .saveas() ---

    @pytest.mark.parametrize(
        "line",
        [
            'doc.saveas("output.dxf")',
            "drawing.saveas(output_path)",
        ],
    )
    def test_saveas_pattern_matches(self, line: str) -> None:
        """.saveas() pattern catches DXF file-save calls."""
        assert _SAVEAS_RE.search(line), f"Pattern should match: {line!r}"

    def test_saveas_not_in_unapproved_files(self) -> None:
        """No unapproved Python file contains a .saveas() call."""
        violations = _find_pattern_outside_approved(_SAVEAS_RE)
        assert violations == [], ".saveas() found outside approved modules:\n" + "\n".join(
            violations
        )

    # --- entity.dxf.X = ... ---

    @pytest.mark.parametrize(
        "line",
        [
            "entity.dxf.color = 1",
            "entity.dxf.layer = 'WALLS'",
            "entity.dxf.insert = (0, 0, 0)",
        ],
    )
    def test_entity_attr_write_pattern_matches(self, line: str) -> None:
        """entity.dxf.X = ... pattern catches attribute-mutation writes."""
        assert _ENTITY_ATTR_WRITE_RE.search(line), f"Pattern should match: {line!r}"

    @pytest.mark.parametrize(
        "line",
        [
            "if entity.dxf.color == 1:",
            "assert entity.dxf.layer == 'WALLS'",
            "entity.dxf.color != 0",
        ],
    )
    def test_entity_attr_comparison_not_flagged(self, line: str) -> None:
        """Comparison operators (== !=) are reads, not mutations — must not match."""
        assert not _ENTITY_ATTR_WRITE_RE.search(line), (
            f"Pattern should NOT match comparison: {line!r}"
        )

    def test_entity_attr_mutation_not_in_unapproved_files(self) -> None:
        """No unapproved Python file mutates entity.dxf attributes."""
        violations = _find_pattern_outside_approved(_ENTITY_ATTR_WRITE_RE)
        assert violations == [], "entity.dxf.X = ... found outside approved modules:\n" + "\n".join(
            violations
        )


# ---------------------------------------------------------------------------
# Check 3: Protected layer dual-enforcement
# ---------------------------------------------------------------------------


class TestCheck3ProtectedLayers:
    """Check 3 verifies protected-layer enforcement exists in the right modules."""

    def test_validators_py_references_protected_layers(self) -> None:
        """validators.py contains the string 'protected_layers'."""
        validators = REPO_ROOT / "src/cad_dxf_agent/core/validators.py"
        assert validators.exists(), "validators.py missing"
        assert "protected_layers" in validators.read_text(), (
            "validators.py must reference 'protected_layers'"
        )

    def test_tool_executor_py_references_protected(self) -> None:
        """tool_executor.py contains the string 'protected'."""
        tool_executor = REPO_ROOT / "src/cad_dxf_agent/llm/tool_executor.py"
        assert tool_executor.exists(), "tool_executor.py missing"
        assert "protected" in tool_executor.read_text(), (
            "tool_executor.py must reference 'protected'"
        )

    @pytest.mark.parametrize("layer", ["TITLE", "TITLEBLOCK", "SEAL", "REVISION"])
    def test_config_schema_defines_each_protected_layer(self, layer: str) -> None:
        """config_schema.py declares each canonical protected layer by name."""
        config_schema = REPO_ROOT / "src/cad_dxf_agent/models/config_schema.py"
        assert config_schema.exists(), "config_schema.py missing"
        assert layer in config_schema.read_text(), (
            f"Canonical protected layer '{layer}' missing from config_schema.py"
        )

    def test_config_schema_layers_appear_on_one_line(self) -> None:
        """All four layers appear on a single line (the script's regex requirement).

        The script uses the pattern ``TITLE.*TITLEBLOCK.*SEAL.*REVISION`` as a
        single-line grep, so all four names must co-exist on one line in
        config_schema.py (the default-factory list).
        """
        config_schema = REPO_ROOT / "src/cad_dxf_agent/models/config_schema.py"
        script_pattern = re.compile(r"TITLE.*TITLEBLOCK.*SEAL.*REVISION")
        assert script_pattern.search(config_schema.read_text()), (
            "config_schema.py must have all four protected layers on one line; "
            "the script grep uses: TITLE.*TITLEBLOCK.*SEAL.*REVISION"
        )


# ---------------------------------------------------------------------------
# Check 4: No .env files committed
# ---------------------------------------------------------------------------


class TestCheck4NoEnvFiles:
    """Check 4 ensures no .env files are tracked by git."""

    def test_no_env_files_tracked_by_git(self) -> None:
        """git ls-files reports no .env files (excluding .env.example)."""
        result = subprocess.run(
            ["git", "ls-files", "*.env", ".env*", "web/.env*"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        tracked = [
            f for f in result.stdout.strip().splitlines() if f and not f.endswith(".env.example")
        ]
        assert tracked == [], (
            "Found tracked .env files — remove with git rm --cached:\n" + "\n".join(tracked)
        )

    def test_env_example_exclusion_logic(self) -> None:
        r"""Files ending in .env.example are permitted; bare .env files are not.

        This mirrors the ``grep -v '\.env\.example$'`` exclusion in the script.
        """
        candidates = [".env.example", "web/.env.example", ".env", "web/.env", "secrets.env"]
        violations = [f for f in candidates if not f.endswith(".env.example")]
        assert ".env.example" not in violations
        assert "web/.env.example" not in violations
        assert ".env" in violations
        assert "web/.env" in violations
        assert "secrets.env" in violations


# ---------------------------------------------------------------------------
# Check 5: No google.adk imports outside the adk/ module
# ---------------------------------------------------------------------------


class TestCheck5AdkImports:
    """Check 5 ensures google.adk usage is confined to src/cad_dxf_agent/adk/."""

    @pytest.mark.parametrize(
        "line",
        [
            "from google.adk import Agent",
            "from google.adk.agents import LlmAgent",
            "import google.adk",
        ],
    )
    def test_adk_import_pattern_matches(self, line: str) -> None:
        """Pattern correctly identifies google.adk import statements."""
        assert _ADK_IMPORT_RE.search(line), f"Pattern should match: {line!r}"

    @pytest.mark.parametrize(
        "line",
        [
            "from google.cloud import storage",
            "import google.cloud.aiplatform",
            "from google.generativeai import GenerativeModel",
            "# from google.adk import Agent",  # comment
            "    from google.adk import Agent",  # indented — not top-level
        ],
    )
    def test_non_adk_google_import_not_flagged(self, line: str) -> None:
        """Other google.* imports are not mistaken for google.adk."""
        assert not _ADK_IMPORT_RE.search(line), f"Pattern should NOT match: {line!r}"

    def test_no_rogue_adk_imports_in_src(self) -> None:
        """No google.adk imports exist outside src/cad_dxf_agent/adk/ right now."""
        src_root = REPO_ROOT / "src"
        adk_dir = src_root / "cad_dxf_agent" / "adk"
        violations: list[str] = []
        for py_file in src_root.rglob("*.py"):
            try:
                py_file.relative_to(adk_dir)
                continue  # file is inside the approved adk/ module
            except ValueError:
                pass
            if _ADK_IMPORT_RE.search(py_file.read_text(errors="replace")):
                violations.append(str(py_file.relative_to(REPO_ROOT)))
        assert violations == [], "google.adk imported outside approved adk/ module:\n" + "\n".join(
            violations
        )


# ---------------------------------------------------------------------------
# Check 6: Gateway must not import google.adk
# ---------------------------------------------------------------------------


class TestCheck6GatewayNoAdk:
    """Check 6 enforces the gateway-as-pure-proxy rule (no ADK coupling)."""

    def test_gateway_file_exists(self) -> None:
        """The gateway file web/backend/main.py is present."""
        main_py = REPO_ROOT / "web" / "backend" / "main.py"
        assert main_py.exists(), "web/backend/main.py not found"

    def test_gateway_does_not_import_google_adk(self) -> None:
        """web/backend/main.py contains no google.adk import."""
        main_py = REPO_ROOT / "web" / "backend" / "main.py"
        content = main_py.read_text()
        assert not _ADK_IMPORT_RE.search(content), (
            "web/backend/main.py must not import google.adk — "
            "the gateway is a pure proxy with no ADK dependency."
        )

    def test_adk_detection_distinguishes_from_google_cloud(self) -> None:
        """ADK pattern does not accidentally flag other google.* modules."""
        gateway_like_approved = (
            "from google.cloud import storage\n"
            "import google.auth\n"
            "from google.oauth2 import credentials\n"
        )
        assert not _ADK_IMPORT_RE.search(gateway_like_approved), (
            "Pattern incorrectly flagged approved google.* imports"
        )

    def test_adk_detection_catches_gateway_violation(self) -> None:
        """Pattern matches when google.adk appears as it would in a violation."""
        gateway_violation = (
            "from fastapi import FastAPI\nfrom google.adk import Agent\napp = FastAPI()\n"
        )
        assert _ADK_IMPORT_RE.search(gateway_violation), (
            "Pattern should have matched google.adk import in gateway code"
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_pattern_outside_approved(pattern: re.Pattern[str]) -> list[str]:
    """Return relative paths of src/ files that match *pattern* and are not approved."""
    src_root = REPO_ROOT / "src"
    violations: list[str] = []
    for py_file in src_root.rglob("*.py"):
        relative = str(py_file.relative_to(REPO_ROOT))
        if relative in APPROVED_MUTATION_FILES:
            continue
        if pattern.search(py_file.read_text(errors="replace")):
            violations.append(relative)
    return violations
