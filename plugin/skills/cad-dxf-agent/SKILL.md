---
name: cad-dxf-agent
description: Analyzes DXF drawings deterministically — ADA/IBC code compliance, drawing health and QA, quantity takeoff, plain-English summaries, RFI generation, and room/zone detection — with no LLM or API key. Use when a user has a .dxf file and wants to check code compliance, audit drawing quality, pull quantities, summarize a drawing, generate RFIs, or detect rooms and areas. Trigger with "analyze this DXF", "check compliance", "drawing health", "quantity takeoff", "summarize this drawing", "generate RFIs", "detect zones", or "/cad-dxf-agent".
allowed-tools: Read, Glob, Bash(cad-analyze:*), Bash(cad-revision:*), Bash(pip:*), Bash(python:*), Bash(python3:*), AskUserQuestion
argument-hint: a path to a .dxf file (and optionally which check — compliance, health, takeoff, summary, rfi, zones)
version: 0.1.0
author: Jeremy Longshore <jeremy@intentsolutions.io>
license: Apache-2.0
compatibility: Designed for Claude Code, also compatible with Codex and OpenClaw
tags:
  - dxf
  - cad
  - compliance
  - takeoff
  - drawing-analysis
---

# cad-dxf-agent — DXF Drawing Analysis

## Overview

CAD reviewers manually scan drawings for code compliance, QA defects, quantities,
and ambiguities — slow and error-prone. This skill automates that for DXF files by
driving the deterministic `cad-analyze` CLI (no LLM, no API key, no network) and
reporting the findings in prose.

| Capability | What it answers | Command |
|---|---|---|
| **compliance** | Does it meet ADA / IBC / a custom code? | `cad-analyze compliance FILE [--profile ada\|ibc-2021\|residential]` |
| **health** | Is the drawing clean? (overlaps, text, orphan layers) | `cad-analyze health FILE` |
| **takeoff** | How much of everything? (counts, lengths, areas) | `cad-analyze takeoff FILE` |
| **summary** | What is this drawing, in plain English? | `cad-analyze summary FILE` |
| **rfi** | What's ambiguous / needs clarification? | `cad-analyze rfi FILE` |
| **zones** | What rooms/areas are enclosed, and how big? | `cad-analyze zones FILE` |
| **compare** | What changed between two revisions? | `cad-revision diff MASTER REVISION` |

## Prerequisites

The CLI ships with the `cad-dxf-agent` Python package. Check, install only if missing:

```bash
command -v cad-analyze >/dev/null 2>&1 || \
  pip install "git+https://github.com/jeremylongshore/cad-ai-agent.git"
```

(If the package is on PyPI, `pip install cad-dxf-agent` also works.)

## Instructions

1. **Locate the DXF.** If the user named a file, use it; otherwise `Glob` for
   `**/*.dxf` and, if several match, ask which one with `AskUserQuestion`.
2. **Pick the capability** from the trigger words. If unclear, ask.
3. **Run the CLI with `--json`** and capture stdout, e.g. `cad-analyze health DRAWING.dxf --json`.
4. **Parse the JSON and report in prose** (see Output). For **compliance**, pass
   `--profile` when the user names a code; default `ada`.

See `references/capabilities.md` for each report's JSON shape.

## Output

Report in prose, not raw JSON. Lead with the headline, then the notable entries:

- **compliance** → `violation_count` + each `findings[]` (rule, evidence handles).
- **health** → `score` (0–100) + `issues[]` grouped by `severity`.
- **takeoff** → the `items[]` quantities (name / quantity / unit) by category.
- **summary** → the plain-English narrative + room list.
- **rfi** → the generated questions as a numbered list a reviewer can send.
- **zones** → detected rooms/areas with computed areas.

Always quote the drawing's own evidence (entity handles, layers) so the user can act.

## Error Handling

- Exit `0` = ok; `1` = compliance violations present (valid JSON still on stdout —
  parse it, then state the drawing fails on N items); `2` = file not found / unreadable.
- `cad-analyze: command not found` → run the Prerequisites install, then retry.
- Empty `findings`/`issues` list = the drawing **passed** that check. Report that;
  never invent or pad findings.

## Examples

**"Check this floor plan for ADA compliance."**
```bash
cad-analyze compliance ./plans/level-1.dxf --profile ada --json
```
Read `violation_count`; if `> 0`, summarize each violation with its rule and
evidence handles, then state the drawing fails ADA on N items.

**"How clean is drawing.dxf?"**
```bash
cad-analyze health drawing.dxf --json
```
Report the `score`, then group `issues[]` by `severity` — e.g. "9 overlapping-entity
locations and inconsistent text heights on layer NOTES."

## Safety

- **Read-only.** Analysis never modifies the DXF. `cad-revision apply`/`bundle`
  writes a **new** file (save-as) — the original is never touched.
- **Offline.** The analysis capabilities make no network calls and use no secrets.

Natural-language *editing* and agent-mode tool use require a bring-your-own LLM
provider (`CAD_LLM_PROVIDER=module:Class`) and are not exposed here — this skill
is analysis plus revision comparison only.

## Resources

- `references/capabilities.md` — JSON shape of each report and how to read it.
- Source + issues: <https://github.com/jeremylongshore/cad-ai-agent>
- `cad-analyze --help` / `cad-revision --help` — full CLI surface.
