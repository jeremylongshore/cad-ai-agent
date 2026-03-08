# 058-AT-ARCH — IntentCAD v0.8.0 UI/UX Design Strategy

**Epics:** EPIC-CAD-13, EPIC-CAD-14, EPIC-CAD-15
**Phase:** 6
**Created:** 2026-03-07
**Design System:** `design-system/intentcad-v0.8.0/MASTER.md`

---

## Design Philosophy

IntentCAD serves CAD professionals — architects, engineers, landscape designers — who value **precision and clarity** over visual flair. The UI must feel like a serious production tool, not a demo. Every pixel earns its place by reducing friction or increasing confidence.

**Core principle:** Data-Dense Dashboard with progressive disclosure. Show what matters, hide what doesn't, reveal on demand.

## Design System Summary

| Token | Value | Usage |
|-------|-------|-------|
| Primary | `#0F172A` | Headers, nav, primary text |
| Secondary | `#1E293B` | Panels, sidebars, cards |
| CTA / Success | `#22C55E` | Apply, confirm, success states |
| Warning | `#F97316` | Ambiguity flags, attention needed |
| Error | `#EF4444` | Blockers, validation failures |
| Background | `#020617` | App background (dark mode) |
| Surface | `#0F172A` | Card/panel backgrounds |
| Text Primary | `#F8FAFC` | Body text |
| Text Muted | `#94A3B8` | Secondary labels, timestamps |
| Border | `#334155` | Panel borders, dividers |

**Typography:** Fira Code (headings, entity handles, measurements) / Fira Sans (body, labels, descriptions)
**Icons:** Lucide React (consistent 24x24 SVG, no emojis)
**Transitions:** 150-300ms for micro-interactions, ease-out
**Z-index scale:** 10 (panels), 20 (dropdowns), 30 (modals), 50 (toasts)

## Layout Evolution

### Current (v0.7.0)
```
┌─────────────────────────────────────────────────────┐
│ Header (logo + auth)                                │
├──────────────┬──────────────────────────────────────┤
│ Left Panel   │ Right Panel                          │
│ (Chat/Upload)│ (DXF Viewer)                         │
│              │                                      │
│              │                                      │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

### Target (v0.8.0)
```
┌─────────────────────────────────────────────────────┐
│ Header (logo + ActiveDrawingBadge + auth)           │
├────────┬─────────────┬──────────────────────────────┤
│ Doc    │ Left Panel  │ Right Panel                  │
│ Library│ (Chat +     │ (DXF Viewer)                 │
│ (new)  │  Pipeline + │                              │
│        │  Preview +  │                              │
│        │  Precision) │                              │
│        │             │                              │
└────────┴─────────────┴──────────────────────────────┘
```

**Key change:** Three-column layout. Document library as a collapsible left rail. Existing left panel becomes the interaction column. Right panel unchanged.

## Component Design — EPIC-CAD-15: Document Library

### DocumentLibrary (sidebar rail)
- **Width:** 240px expanded, 48px collapsed (icon-only)
- **Toggle:** Hamburger icon or keyboard shortcut
- **Sort:** Last accessed (default), name, upload date
- **Empty state:** Upload prompt with drag-drop zone
- **Overflow:** Virtual scroll for 50+ documents

### DocumentCard
- **Layout:** Filename (truncated, tooltip on hover) + upload date + file size
- **States:** Default, hover (highlight), active (blue left border), loading
- **Actions:** Click to load, right-click context menu (delete, info)
- **Active indicator:** Solid left border in CTA green

### UploadToLibrary
- **Trigger:** "+" button in library header + drag-drop on library panel
- **Flow:** Select file → upload progress bar → appear in library
- **Validation:** File type (DXF only), size limit (25MB), quota check
- **Error states:** File too large, quota exceeded, invalid format

### ActiveDrawingBadge (workspace header)
- **Content:** Filename + "Saved" / "Modified" indicator
- **Position:** Center of header bar
- **Purpose:** Always-visible context — which drawing am I looking at?

## Component Design — EPIC-CAD-14: Precision Controls

### PrecisionPanel (expandable)
- **Trigger:** "Advanced" toggle below chat input, or keyboard shortcut
- **Collapsed state:** Single line: "Advanced controls" with chevron
- **Expanded state:** Grouped form sections:
  - **Targeting:** Handle input, layer multi-select, type checkboxes
  - **Scope:** Model space toggle, exclude layers
  - **Thresholds:** Confidence slider (0-100%), inference toggle
  - **Measurements:** Exact delta inputs with unit selector
- **Persistence:** Panel state remembered per session

### CandidateList (inline in chat)
- **Trigger:** Automatic when ambiguity detected (3+ matches)
- **Layout:** Numbered list of MatchCandidate cards inline in chat flow
- **Card content:** Entity handle (monospace), layer, type, confidence %, match reason
- **Selection:** Click to select, enter to confirm, or type number
- **Dismissal:** "Use best match" button to accept highest confidence

### ActionDetailView (in preview)
- **Position:** Below existing preview summary, collapsed by default
- **Content:** Per-entity action table: handle, action, before → after, status
- **Status badges:** Planned (blue), Applied (green), Skipped (yellow), Blocked (red)
- **Export:** "Download audit log" button → JSON/CSV

## Component Design — EPIC-CAD-13: Objective Pipeline

### StagePipeline (progress indicator)
- **Position:** Top of left panel, below chat header
- **Layout:** Horizontal step indicator: Analyze → Recommend → Plan → Preview
- **States per stage:** Pending (gray), Active (pulsing blue), Complete (green check), Skipped (dashed)
- **Interaction:** Click completed stage to view its output

### StageGateCard (checkpoint between stages)
- **Position:** Inline in chat flow between stage outputs
- **Content:** Stage summary + "Continue" / "Modify" / "Stop" buttons
- **Collapsible:** Shows output summary, expandable to full detail
- **Visual:** Horizontal rule with stage name badge

### RecommendationCard (recommend stage output)
- **Layout:** Card per option with title, description, estimated impact, tradeoffs
- **Selection:** Radio-button style — select one to proceed to plan stage
- **Confidence:** Subtle confidence bar at card bottom
- **Tradeoffs:** Bulleted list with pro (green) / con (orange) indicators

## Accessibility Requirements

- WCAG AA minimum (4.5:1 contrast ratio for all text)
- Keyboard navigation for all interactive elements
- Tab order matches visual flow (left rail → interaction panel → viewer)
- Focus rings on all interactive elements (2px solid blue outline)
- `aria-label` on all icon-only buttons
- `prefers-reduced-motion` respected (disable transitions)
- Screen reader: `aria-live="polite"` for stage progress updates
- Skip links: "Skip to drawing viewer" for keyboard users

## Responsive Behavior

| Breakpoint | Document Library | Left Panel | Right Panel |
|------------|-----------------|------------|-------------|
| >= 1280px | Expanded sidebar | Full width | Full width |
| 1024-1279px | Collapsed (icons) | Full width | Full width |
| 768-1023px | Hidden (overlay) | Full width | Tabbed with viewer |
| < 768px | Hidden (overlay) | Full width | Stacked below |

## Implementation Sequence

1. **Design tokens** — CSS custom properties file with all tokens from this doc
2. **DocumentLibrary** (EPIC-CAD-15) — Highest priority, unblocks everything
3. **ActiveDrawingBadge** — Simple, high-visibility improvement
4. **PrecisionPanel** (EPIC-CAD-14) — Progressive disclosure foundation
5. **CandidateList** — Ambiguity UX, inline in existing chat
6. **StagePipeline** (EPIC-CAD-13) — Pipeline visualization
7. **RecommendationCard** — Objective output display
8. **ActionDetailView** — Preview enhancement

## Pre-Delivery Checklist

- [ ] No emojis as icons (Lucide React throughout)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with 200ms transitions
- [ ] Light/dark mode contrast verified
- [ ] Focus states visible for keyboard nav
- [ ] `prefers-reduced-motion` respected
- [ ] Tested at 375px, 768px, 1024px, 1440px
- [ ] Entity handles rendered in Fira Code (monospace)
- [ ] All panel states survive page refresh (localStorage)
