# Release Report: cad-dxf-agent v0.2.0

## Executive Summary

- **Version**: 0.2.0
- **Release Date**: 2026-02-25
- **Release Type**: MINOR
- **Approved By**: jeremy
- **Duration**: ~27 minutes

## Pre-Release State

### Pull Requests
- Merged before release: 0 (all PRs already merged)
- Deferred: 0
- Blocked: 0

### Branch State
- beads-sync: 9 commits ahead (expected, beads state tracking)
- No stale branches requiring cleanup

### Security
- Secrets scan: PASS (no exposed credentials)
- Dependency audit: Not enabled (Dependabot disabled)

## Changes Included

### Features
- **Web MVP**: Firebase Hosting frontend + Cloud Run backend with 65-test suite
- Paper space / layout editing support
- Windows packaging & installer infrastructure
- Live Gemini API test infrastructure with WIF-based CI
- Responsive pipeline with QThread worker and progress UI
- Planner hardening: drawing stats, deterministic execution, trace view
- Vision pipeline integration with PDF-to-edit conversion
- Validation feedback loop for planner self-correction
- Live PDF-to-edit full journey tests
- v0.2.0 testing infrastructure: ScriptedAgentProvider, golden trajectories
- Max snapshots cap to EditHistory (default 50)
- Validator micro-benchmarks in CI

### Fixes
- Handle pymupdf 1.27 quad item API change in PDF converter
- Web backend deps: google-cloud-aiplatform and matplotlib
- Strip mocks from web test suite, fix anonymous auth error handling
- Use ADC auto-detection for live API tests
- Resolve critical audit findings for v0.1.0

### Breaking Changes
- None

## Documentation Updates

### README Changes
- Updated V1 Scope table to "Scope" reflecting current state
- Added Web App section with deployment instructions
- Replaced "Testing With a Real LLM" with "Using Gemini (Vertex AI)"
- Updated project structure to include web/ directory
- Updated test count (573 tests)

### CHANGELOG
- Added [0.2.0] section with 18 categorized entries

## Metrics

| Metric | Value |
|--------|-------|
| Commits | 26 |
| Files Changed | 163 |
| Lines Added | +18,335 |
| Lines Removed | -280 |
| Contributors | 2 |
| Days Since Last Release | 4 |

## Quality Gates

| Gate | Status |
|------|--------|
| Tests Passing | ✓ (573 tests) |
| Secrets Scan | ✓ |
| Dependency Audit | ○ (not enabled) |
| Branch Protection | ○ (not configured) |
| Documentation Current | ✓ |

## Rollback Procedure

If issues discovered:

```bash
# Remove release
git push origin --delete v0.2.0
git tag -d v0.2.0
gh release delete v0.2.0 --yes

# Revert changes
git revert HEAD
git push origin main
```

## Post-Release Checklist

- [x] Tag pushed to remote
- [x] GitHub release created
- [x] Version files consistent (0.2.0)
- [ ] Monitor error rates for 24h
- [ ] Check user feedback channels
- [ ] Update project board/roadmap
