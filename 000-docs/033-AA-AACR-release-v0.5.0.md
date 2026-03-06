# Release Report: cad-dxf-agent v0.5.0

## Executive Summary

- **Version**: v0.5.0
- **Release Date**: 2026-03-06
- **Release Type**: MINOR
- **Previous Version**: v0.4.0 (2026-03-02)
- **Approved By**: jeremy
- **GitHub Release**: https://github.com/jeremylongshore/cad-dxf-agent/releases/tag/v0.5.0

## Pre-Release State

### Pull Requests
- Merged before release: 1 (PR #69 — dependabot docker/login-action)
- Open/deferred: 1 (PR #64 — DWG ODA support, WIP)
- Blocking issues resolved: ruff format compliance on 3 files

### Pre-Release Actions Required
- Fixed `ruff format` compliance failures in `converter.py`, `renderer.py`, `test_pdf_classifier.py`
- Rebased and merged dependabot PR #69 after formatting fix unblocked lint CI

### Branch State
- 3 merged branches cleaned: `fix/e2e-auth-sidebar`, `fix/pdf-colors-classifier`, `fix/pdf-noise-filter`
- `beads-sync` and `feat/dwg-oda-support` preserved

### Security
- Vulnerabilities addressed: 0
- Secrets scan: PASS
- npm audit: 0 critical, 0 high, 0 moderate
- Dependabot alerts: 0 open

## Changes Included

### Features (3)
- **Interactive WebGL Viewer**: Hardware-accelerated DXF rendering with pan/zoom/rotate in browser (#63)
- **Compare Tab UX Overhaul**: Streamlined revision comparison workflow with improved side-by-side views (#65)
- **DWG on Cloud Run**: Server-side DWG-to-DXF conversion via ODA File Converter for web uploads

### Fixes (9)
- Filter sub-pixel noise entities from PDF extraction to reduce false matches (#68)
- PDF entity colors, classifier heuristics, and render quality guard (#67)
- E2E global auth setup and sidebar close behavior (#66)
- Fetch timeouts, friendly error messages, and request logging in web backend
- Anonymous Firebase users bypass license check
- Docker ODA install made optional with file-size guard
- E2E test stability: sourced upload batching, suggestion chips, alignment confidence

### Dependencies
- Bump docker/login-action from 3 to 4 (#69)

## Documentation Updates

### CHANGELOG.md
- Added `[0.5.0] - 2026-03-06` section with 18 entries

### README.md
- Updated test count: ~573 → ~1375
- Updated coverage: 68%+ → 95%

## Metrics

| Metric | Value |
|--------|-------|
| Commits | 19 |
| Files Changed | 83 |
| Lines Added | +7,606 |
| Lines Removed | -301 |
| PRs Merged | 1 (dependabot) |
| Branches Cleaned | 3 |
| Days Since Last Release | 4 |

## Quality Gates

| Gate | Status |
|------|--------|
| Lint | PASS |
| Type Check | PASS |
| Tests (Ubuntu 3.11) | PASS |
| Tests (Ubuntu 3.12) | PASS |
| Tests (Windows 3.11) | PASS |
| Tests (Windows 3.12) | PASS |
| Bandit Security | PASS |
| pip-audit | PASS |
| Secrets Scan | PASS |
| npm audit | PASS |

## Testing Improvements

| Metric | v0.4.0 | v0.5.0 |
|--------|--------|--------|
| Test count | ~1150 | 1375 |
| Coverage | 89% | 95% |
| E2E tests added | — | +36 (WebGL viewer, sourced uploads) |

## Known Issues / Notes

- `LICENSE` file missing from repo (README claims MIT) — add in next release
- PR #64 (DWG ODA support) remains open (WIP)
- `gui-test` CI check failed on dependabot PR (not a required check; infrastructure issue)

## Rollback Procedure

```bash
# Remove release
git push origin --delete v0.5.0
git tag -d v0.5.0
gh release delete v0.5.0 --yes

# Revert release commit
git revert HEAD
git push origin main
```

## Post-Release Checklist

- [x] GitHub release created with full changelog
- [x] Tag v0.5.0 pushed
- [x] CHANGELOG.md updated
- [x] README.md test counts updated
- [x] Merged branches cleaned (3 branches)
- [ ] Monitor deploy-web.yml workflow (auto-triggered by main push)
- [ ] Announce in relevant channels
