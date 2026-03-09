# Mutation Testing Practices — cad-dxf-agent

> Branch: feature/audit-fixes-security-and-stability · Created: 2026-03-08
> Related: 055-TQ-AUDT (test audit report), PR #111

---

## Why Mutation Testing

Traditional code coverage (line/branch) answers "was this code executed?" but not "would tests catch a bug here?" Mutation testing answers the harder question by systematically injecting faults and checking if tests detect them.

We adopted mutation testing after an honest audit of PR #111's 138 AI-written tests found 42 bias patterns — tautological assertions, smoke-only checks, and self-referential tests that confirmed existing behavior rather than stress-testing correctness.

## Tool: mutmut v3.5.0

### Configuration (pyproject.toml)

```toml
[tool.mutmut]
paths_to_mutate = [
    "src/cad_dxf_agent/core/design_ops.py",
    "src/cad_dxf_agent/core/construction_ops.py",
    "src/cad_dxf_agent/core/comparison/geometry.py",
]
tests_dir = ["tests/unit/"]
also_copy = ["src/", "web/", "tests/helpers/", "scripts/"]
```

### Key v3 differences from v2

- Config lives in `pyproject.toml`, not CLI flags (v2 `--paths-to-mutate` doesn't work)
- mutmut copies project to `mutants/` sandbox — `also_copy` must include everything needed for `pip install -e .` and test imports
- Run with `mutmut run --max-children 4` (parallelism)
- Results via `mutmut results` (surviving mutants) and `mutmut show <id>` (specific diffs)

### Running

```bash
# Full run (~10 min with 4 workers on 3 source files, 2187 mutants)
rm -rf .mutmut-cache mutants/ && .venv/bin/mutmut run --max-children 4

# Analyze survivors by function
mutmut results 2>&1 | sed 's/__mutmut_[0-9]*//' | sort | uniq -c | sort -rn

# View a specific surviving mutant
mutmut show cad_dxf_agent.core.design_ops.xǁScopeBuilderǁbuild__mutmut_7
```

## Kill Rate Progression

| Round | Tests added | Kill rate | Mutants killed | Date |
|-------|------------|-----------|----------------|------|
| Baseline (PR #111) | 138 | ~65% (est.) | — | 2026-03-07 |
| Round 1: Fix 10 worst + 8 negative cases | 18 | 72% (1574/2187) | 1574 | 2026-03-08 |
| Round 2: 161 targeted mutation killers | 161 | 77% (1681/2187) | +107 | 2026-03-08 |
| Round 3: 258 deep mutation killers | 258 | **86.1%** (1883/2187) | +202 | 2026-03-08 |

**Target: 85% kill rate** (15 points above the 70% industry standard). **Achieved: 86.1%.**

## Common Surviving Mutant Patterns and How to Kill Them

### 1. None vs empty string (`None` → `""`)

**Problem:** Tests using `assert not result.field` pass for both `None` and `""`.

**Fix:** Use identity checks:
```python
# BAD - passes for both None and ""
assert not snapshot.text_content

# GOOD - only passes for None
assert snapshot.text_content is None
```

### 2. Coordinate swaps (`p[0]` → `p[1]`)

**Problem:** Tests with square/symmetric coordinates (e.g., `(100, 100)`) can't detect x/y swaps.

**Fix:** Always use asymmetric coordinates:
```python
# BAD - swap undetectable
msp.add_line((100, 100), (200, 200))

# GOOD - swap produces wrong result
msp.add_line((100, 200), (300, 400))
assert snapshot.points[0].x == 100
assert snapshot.points[0].y == 200
```

### 3. Default value mutations (`1.0` → `2.0`)

**Problem:** Tests only exercise entities WITH explicit attribute values, so the default path is untested.

**Fix:** Create entities WITHOUT the attribute set, so the default is the only source of the value:
```python
# INSERT without explicit scale → default xscale=1.0
insert = msp.add_blockref("BLK", (0, 0))
# Don't set insert.dxf.xscale — let it use the default
snapshot = _extract_one(insert, "INSERT")
assert snapshot.attributes["insert_xscale"] == 1.0  # catches 1.0→2.0 mutation
```

### 4. String literal mutations (case, "XX" prefix)

**Problem:** Tests using `assert "keyword" in result` pass for `"XXkeywordXX"` and `"KEYWORD"`.

**Fix:** Assert exact strings or use equality:
```python
# BAD - passes for "XXNo entities in drawing.XX"
assert "No entities" in result.caveats[0]

# GOOD - catches case/prefix mutations
assert result.caveats[0] == "No entities in drawing."
```

### 5. Tautological assertions (`x == sorted(x)`)

**Problem:** If the source always returns sorted data, `assert x == sorted(x)` is a tautology.

**Fix:** Assert the specific expected order:
```python
# BAD - always passes if source sorts
assert areas == sorted(areas)

# GOOD - specific expected values
assert areas == ["ELECTRICAL", "HVAC", "PLUMBING"]
```

### 6. Self-referential assertions

**Problem:** `assert entry.count == len(entry.items)` confirms implementation, not correctness.

**Fix:** Assert against known input values:
```python
# BAD - confirms code agrees with itself
assert result.total == len(result.items)

# GOOD - confirms code against known input
assert result.total == 5  # we added exactly 5 entities
```

### 7. Smoke-only checks (`result is not None`)

**Problem:** Passes even if every field is wrong.

**Fix:** Assert specific field values:
```python
# BAD
assert result is not None

# GOOD
assert result.confidence == 0.7
assert result.grid_lines == 8
assert result.description.startswith("Detected 4 horizontal")
```

### 8. Loop logic mutations (`continue` → `break`)

**Problem:** Tests with single-element input can't distinguish continue from break.

**Fix:** Use multi-element inputs where ALL elements must be processed:
```python
# Create 5 entities — all must appear in output
for i in range(5):
    msp.add_line((0, i * 100), (1000, i * 100))
result = analyzer.analyze(context)
assert len(result.grid_lines) == 5  # catches break-after-first
```

## Equivalent Mutants (Unkillable)

Some mutations don't change observable behavior and can never be killed:

- **Logger message changes** — `logger.debug("X %s", handle)` → `logger.debug(None, handle)`. Unless you mock the logger and assert on call args (testing implementation, not behavior), these survive.
- **Comment mutations** — mutmut doesn't mutate comments, but some tools do.
- **Dead code mutations** — code paths that are unreachable by design.

These are expected survivors and don't count against test quality. A realistic ceiling for kill rate on code with logging is ~90-92%, not 100%.

## When to Run Mutation Testing

- **Before merging test PRs** — validates test quality, not just quantity
- **After major refactors** — ensures tests still catch bugs, not just regressions
- **Quarterly audit** — spot-check core modules for test drift

Mutation testing is slow (~10 min for 2187 mutants). Don't run in CI — run locally before important merges.

## Files Involved

| File | Purpose |
|------|---------|
| `src/cad_dxf_agent/core/design_ops.py` | Layout, revision summary, takeoff (917 mutants) |
| `src/cad_dxf_agent/core/construction_ops.py` | Grid, markup, batch condition (647 mutants) |
| `src/cad_dxf_agent/core/comparison/geometry.py` | Geometry extraction, xref detection (623 mutants) |
| `tests/unit/test_design_ops.py` | 223 tests |
| `tests/unit/test_construction_ops.py` | 197 tests |
| `tests/unit/test_comparison_geometry.py` | 158 tests |
| `pyproject.toml` | mutmut configuration (`[tool.mutmut]` section) |
