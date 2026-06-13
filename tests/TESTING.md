# Testing Policy

Canonical policy thresholds for this repo. The vendored audit-harness reads the
machine-readable values below (e.g. `escape-scan` uses `coverage.line` as the
floor it refuses to let a diff drop beneath), so this file is the single source
of truth for "what bar must a change clear."

## Policy thresholds

```
coverage.line: 65
coverage.branch: 0
mutation.kill_rate: 0
```

- **`coverage.line: 65`** — enforced in CI via `fail_under = 65` in
  `[tool.coverage.report]` (`pyproject.toml`). `escape-scan` REFUSES any diff
  that lowers a coverage threshold below this floor. Raise both together; never
  ratchet down.
- **`coverage.branch: 0`** — branch coverage is measured but not gated yet.
- **`mutation.kill_rate: 0`** — `mutmut` is configured (`[tool.mutmut]` in
  `pyproject.toml`, three core modules) but not yet gated in CI. Set a real
  floor here when the mutation run is promoted to a required check.

## Enforcement layers in CI

| Layer | Where | Status |
|-------|-------|--------|
| Lint / format (ruff) | `ci.yml` → `lint` | required |
| Types (mypy) | `ci.yml` → `typecheck` | required |
| Unit/integration/web tests + coverage floor | `ci.yml` → `test` | required |
| Architectural drift | `ci.yml` → `drift-check` | required |
| **Harness hash-pin (`verify`)** | `ci.yml` → `audit-harness` | required |
| **Escape-scan (diff)** | `ci.yml` → `audit-harness` | required (PRs) |
| Bias count | `ci.yml` → `audit-harness` | advisory |
| Architecture rules (`arch`) | `ci.yml` → `audit-harness` | advisory (no rule config yet) |

## Promoting advisory gates

The harness can do more than is gated today. To promote a gate from advisory to
required:

1. **Architecture rules** — add an `.importlinter` contract (layered:
   `models` ← `core`/`llm` ← `cli`/`ui`/`web`), then make the `arch` step
   blocking.
2. **Mutation** — wire a `mutmut run` step, set `mutation.kill_rate` above, and
   make it blocking.

After any change to a pinned policy artifact, re-run `scripts/audit-harness init`
and commit the updated `.harness-hash` in the same change.
