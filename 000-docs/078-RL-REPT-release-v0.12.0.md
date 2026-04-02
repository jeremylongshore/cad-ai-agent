# Release Report: cad-dxf-agent v0.12.0

## Executive Summary

- **Version**: 0.12.0
- **Release Date**: 2026-04-01
- **Release Type**: MINOR
- **Approved By**: jeremy
- **Duration**: ~25 minutes
- **GitHub Release**: https://github.com/jeremylongshore/cad-dxf-agent/releases/tag/v0.12.0

## Pre-Release State

### Pull Requests
- Merged before release: 6 (#141, #146, #147, #148, #150, #151)
- Closed as redundant: 1 (#149 — changes covered by #146 + #148 + #150)
- Deferred: 0
- Blocked: 0

### Code Review
- Gemini + Qodo reviews checked on all 6 PRs
- Fixes applied: PR #150 `disabledTitle` priority logic, PR #141 `.pdf` → `.md` references
- Already addressed from prior session: PR #147 `return false` default, PR #148 `prefers-reduced-motion`
- Cosmetic suggestions deferred (inline styles → CSS classes) — consistent with existing codebase

### Branch State
- 7 merged branches deleted (remote + local)
- 1 stale worktree cleaned up
- `beads-sync` branch preserved (required by beads tooling)

### Security
- Secrets scan: PASS (no credentials in diff)
- Python dependency audit: PASS (no vulnerabilities)
- Frontend dependency audit: PASS (0 vulnerabilities in production deps)
- 2 Dependabot alerts (picomatch — dev dependency, non-blocking)

## Changes Included

### Features
- **Email/Password Sign-In**: Admin-provisioned accounts alongside Google OAuth (#151)
- **Color-Cycle Selection Highlights**: Multi-entity selection with distinct color cycling and click-to-focus operations (#130)
- **Entity Selection UX**: Click-to-select entities in viewer, diff detection for MODIFIED and MOVED entities (#129)
- **QA Test Infrastructure**: First manual QA pass — 37 test cases covering comparison workflow, 13 issues filed (#141)

### Fixes (QA-driven)
- **Apply Button Tooltip**: Contextual helper text with correct message priority — pending review > zero approved (#150)
- **Keyboard Navigation Scroll**: Ops list scrolls to focused item, respects `prefers-reduced-motion` (#148)
- **Revision Replace Warning**: Confirmation dialog before replacing revision file mid-workflow (#148)
- **Approve After Reject**: Bulk approve/reject filter correctly toggles; `return false` default for safety (#147)
- **New File Confirmation**: Browser confirm dialog prevents accidental workspace reset (#146)

### Changed
- `google-adk` dependency bumped (#131)
- GitHub Sponsors + Buy Me a Coffee funding links added

## Version Artifacts

| Artifact | Before | After |
|----------|--------|-------|
| `src/cad_dxf_agent/__init__.py` | 0.11.0 | 0.12.0 |
| `web/frontend/package.json` | 0.10.1 | 0.12.0 |
| Git tag | v0.11.0 | v0.12.0 |
| CHANGELOG.md | Updated with v0.12.0 section |

## Deploy

- **Method**: GitHub Actions (auto-deploy on push to main)
- **Trigger**: `bde10b0` push to main
- **Artifacts**: Docker image → Cloud Run (backend), Firebase Hosting (frontend)

## Observations

1. **First QA cycle complete**: Ope (opeyemiariyo@intentsolutions.io) ran 37 manual test cases, filed 13 issues. 5 bug fixes shipped in this release, remaining issues tracked for next cycle.
2. **Worktree branch mix-up**: PR #149 was created from a worktree that picked up changes from other branches. The revision replace warning ended up in #148 instead of #149. Closed #149 as redundant. Future fix: verify worktree base before creating PRs.
3. **Frontend version was stale**: `web/frontend/package.json` was still at `0.10.1` (skipped 0.11.0). Synced to 0.12.0 in this release.
4. **Picomatch dev-dep vulnerabilities**: 2 Dependabot alerts for picomatch (high ReDoS, medium method injection). Dev dependency only — not in production bundle. Will address in next dependency sweep.

## Remaining Open Issues

| Issue | Type | Status |
|-------|------|--------|
| #133 | Document Library discoverability | Open — enhancement |
| #134 | Diff badges not visible | Open — investigate |
| #136 | Control point refinement 0% | Open — investigate |
