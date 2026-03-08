# Release Report: cad-dxf-agent v0.7.0

## Executive Summary

- **Version**: 0.7.0
- **Release Date**: 2026-03-07
- **Release Type**: MINOR (feature release)
- **Approved By**: jeremy
- **Approval SHA**: 491850b

## Pre-Release State

### Pull Requests
- PRs merged before release: 6 (#86, #87, #88, #89, #90, #91)
- Deferred: 0
- Blocked: 0

### Branch State
- Branches merged: 6 (epic-cad-08 through epic-cad-12, plus hotfixes)
- Stale branches remaining: 2 (epic-cad-09, epic-cad-10 — squash-merged, safe to delete)

### Security
- Secrets scan: PASS
- Dependency audit: PASS
- Branch protection: Maintained

## Changes Included

### Features
- EPIC-CAD-08: Preview + Apply Workflow (#86)
- EPIC-CAD-09: Design Operations Workflow Pack (#88)
- EPIC-CAD-10: Construction Drawing Workflow Pack (#89)
- EPIC-CAD-11: Session Durability + Scale Readiness (#90)
- EPIC-CAD-12: Evaluation Harness + Quality Governance (#91)
- Drawing rotation controls in preview panel

### Fixes
- Session UX improvements and clarification message handling
- Intent router patterns widened for natural language questions
- Cloud Run resources bumped to 8GB/4CPU/600s for large PDF uploads

### Breaking Changes
- None

## Documentation Updates

### CHANGELOG
- Full v0.7.0 section added with all epics and metrics

### After-Action Reports
- 049-PM-AAR-epic-cad-08-aar.md
- 050-PM-AAR-epic-cad-09-aar.md
- 051-PM-AAR-epic-cad-10-aar.md
- 052-PM-AAR-epic-cad-11-aar.md
- 053-PM-AAR-epic-cad-12-aar.md

## Metrics

| Metric | v0.6.0 | v0.7.0 | Change |
|--------|--------|--------|--------|
| Commits | — | 11 | +11 |
| Files Changed | — | 92 | — |
| Lines Added | — | +17,418 | — |
| Lines Removed | — | -155 | — |
| Tests | 1,924 | 2,468+ | +544 |
| Golden Trajectories | 15 | 27 | +12 |
| Scorecard Entries | 0 | 32 | +32 |
| Task Families Tested | 4 | 9 | +5 |
| Intent Accuracy | — | 96.9% | — |

## Quality Gates

| Gate | Status |
|------|--------|
| Tests Passing | ✓ 2,468+ |
| Secrets Scan | ✓ |
| Branch Protection | ✓ |
| Documentation Current | ✓ |
| All Beads Closed | ✓ (17 closed, 0 open) |
| All Epics Done | ✓ (12/12) |

## Milestone Achievement

**ALL 12 EPICS COMPLETE**

| Phase | Epics | Status |
|-------|-------|--------|
| Phase 1: Foundation | 01, 02, 03 | DONE |
| Phase 2: Core Intelligence | 04, 05, 06, SQ67 | DONE |
| Architecture Review | ARCH-REVIEW-01 | DONE |
| Phase 3: Structured Editing | 07, 08 | DONE |
| Phase 4: Workflow Packs | 09, 10 | DONE |
| Phase 5: Production Readiness | 11, 12 | DONE |

The Drawing Intelligence Platform is now feature-complete.

## Rollback Procedure

If issues discovered:

```bash
# Remove release
git push origin --delete v0.7.0
git tag -d v0.7.0
gh release delete v0.7.0 --yes

# Revert changes
git revert HEAD
git push origin main
```

## Post-Release Checklist

- [x] Tag pushed to remote
- [x] GitHub release created
- [x] CHANGELOG updated
- [x] All beads closed
- [ ] Monitor error rates for 24h
- [ ] Check user feedback channels

---

*Release ceremony executed by Claude Opus 4.6*
