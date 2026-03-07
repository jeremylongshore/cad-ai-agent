# 047 — Release Report: cad-dxf-agent v0.6.0

## Executive Summary

| Field | Value |
|-------|-------|
| **Version** | 0.6.0 |
| **Release Date** | 2026-03-07 |
| **Release Type** | MINOR |
| **Approved By** | jeremy |
| **Duration** | ~25 minutes |
| **Previous Version** | 0.5.0 (2026-03-06) |

## Pre-Release State

### Pull Requests
- Merged before release: 0 (none pending)
- Deferred: 0
- Blocked: 0

### Branch State
- Branches ahead of main: 0
- Stale branches cleaned: 1 (`fix/epic-cad-06-compliance-gaps`)

### Security
- Secrets scan: PASS (no secrets detected)
- License: MIT (compliant)
- Dependency audit: Not run (pip-audit not installed)

## Changes Included

### Features (9)
1. **EPIC-CAD-02**: Core Contracts + Routing Foundation (#74, #75)
2. **EPIC-CAD-03**: Selection + Markup Interpretation Foundation (#77)
3. **EPIC-CAD-04**: Region Q&A Vertical Slice (#78)
4. **EPIC-CAD-05**: Repeated-Condition Detection (#81)
5. **EPIC-CAD-06**: Compare + Diff Service Hardening (#82)
6. **SIDEQUEST-CAD-67**: Text Positional Accuracy (#79)
7. **Multi-user Workspace**: Google auth + email allowlist (#80)
8. **IntentCAD Rebrand**: Web UI branding update
9. **DWG on Cloud Run**: ODA File Converter integration (#64)

### Fixes (3)
1. Firestore rules deploy made non-blocking
2. EPIC-CAD-02 spec compliance (#75)
3. PDF text display + color detection (#72)

### Documentation (6)
1. EPIC-CAD-01: 8 foundation documents (#71, #73)
2. EPIC-CAD-02 AAR (#76)
3. EPIC-CAD-03 doc gaps (#77 post-merge)
4. ARCH-REVIEW-CAD-01: 10-dimension architecture review (#84)

### Breaking Changes
None

## Metrics

| Metric | Value |
|--------|-------|
| Commits | 19 |
| Files Changed | 171 |
| Lines Added | +27,897 |
| Lines Removed | -959 |
| Contributors | 2 |
| Days Since Last Release | 1 |

### Test Results
| Metric | v0.5.0 | v0.6.0 | Delta |
|--------|--------|--------|-------|
| Total Tests | 1,375 | 1,924 | +549 |
| Coverage | 95% | 95.24% | +0.24% |
| Golden Trajectories | 5 | 15 | +10 |
| Task Families | 2 | 4 | +2 |

## Quality Gates

| Gate | Status |
|------|--------|
| Tests Passing | PASS (1651 passed, 5 skipped) |
| Secrets Scan | PASS |
| License Compliance | PASS (MIT) |
| Version Consistency | PASS (all sources show 0.6.0) |
| Documentation Current | PASS |

## Documentation Updates

### CHANGELOG.md
- Added [0.6.0] section with 27 lines documenting all changes

### README.md
- Updated gist link version reference: v0.5.0 → v0.6.0

### Version Files
- `src/cad_dxf_agent/__init__.py`: 0.4.0 → 0.6.0
- `web/frontend/package.json`: 0.1.0 → 0.6.0
- `web/frontend/package-lock.json`: synced

## Rollback Procedure

If issues discovered:

```bash
# Remove release
git push origin --delete v0.6.0
git tag -d v0.6.0
gh release delete v0.6.0 --yes

# Revert changes
git revert HEAD
git push origin main
```

## Post-Release Checklist

- [x] Tag created and pushed
- [x] GitHub release published
- [x] Version files synced
- [x] CHANGELOG updated
- [x] Stale stashes cleaned (3 dropped)
- [ ] Monitor error rates for 24h
- [ ] Check user feedback channels
- [ ] Update external gist if needed

## Platform Roadmap Status

| Phase | Status |
|-------|--------|
| Phase 1: Foundation (EPIC 01-03) | COMPLETE |
| Phase 2: Core Intelligence (EPIC 04-06) | COMPLETE |
| Architecture Review (ARCH-REVIEW-01) | COMPLETE |
| Phase 3: Structured Editing (EPIC 07-08) | NOT STARTED |
| Phase 4: Workflow Packs (EPIC 09-10) | NOT STARTED |
| Phase 5: Production Readiness (EPIC 11-12) | NOT STARTED |

### Prerequisites for Phase 3
Three items from ARCH-REVIEW-01 must be completed before EPIC-07:
1. **P0**: Upload size validation (MAX_UPLOAD_SIZE=25MB)
2. **P1**: Extract shared text utilities to `core/text_utils.py`
3. **P1**: Truncation confidence penalty in RegionContextBuilder

## Release Artifacts

- **GitHub Release**: https://github.com/jeremylongshore/cad-dxf-agent/releases/tag/v0.6.0
- **Changelog**: https://github.com/jeremylongshore/cad-dxf-agent/blob/main/CHANGELOG.md
- **Compare**: https://github.com/jeremylongshore/cad-dxf-agent/compare/v0.5.0...v0.6.0

---

*Release automated with Claude Code release ceremony*
