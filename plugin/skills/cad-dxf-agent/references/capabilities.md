# Capability reference — `cad-analyze` JSON shapes

Each subcommand prints one JSON object on stdout under `--json`. Lead your
summary with the **headline** field, then surface the **list** entries. All
fields come straight from the drawing — never invent them.

## compliance — `cad-analyze compliance <file> [--profile ada|ibc-2021|residential]`

```jsonc
{
  "profile_name": "ADA",
  "violation_count": 2,        // headline — >0 also makes the CLI exit 1
  "warning_count": 1,
  "pass_count": 5,
  "checks_run": ["door_widths", "hallway_widths", "..."],
  "findings": [                // each: severity, rule, description, evidence
    { "severity": "violation", "title": "...", "description": "...", "evidence": [...] }
  ],
  "zone_count": 4, "entity_count": 312
}
```
Report: pass/fail on the profile, then each violation with its evidence (handles/layers).

## health — `cad-analyze health <file>`

```jsonc
{
  "score": 90.0,              // headline — 0..100
  "entity_count": 312, "layer_count": 6,
  "checks_run": ["_check_overlapping_entities", "..."],
  "issues": [                 // each: severity, category, title, description, evidence[], check_name
    { "severity": "warning", "category": "overlap", "title": "...", "description": "...", "evidence": [...] }
  ]
}
```
Report: the score, then the issues grouped by severity.

## takeoff — `cad-analyze takeoff <file>`

```jsonc
{ "items": [ { "name": "Door", "category": "...", "quantity": 12, "unit": "ea",
              "source_layer": "DOORS", "zone_id": null, "entity_handles": [...], "notes": "" } ] }
```
Report: the quantities table (name / quantity / unit), grouped by category.

## summary — `cad-analyze summary <file>`

```jsonc
{ "rooms": [ ... ], "...": "narrative + layer breakdown + key features" }
```
Report: the plain-English narrative and the room list.

## rfi — `cad-analyze rfi <file>`

```jsonc
{ "items": [ { "question": "...", "category": "...", "context": "..." } ] }
```
Report: the generated RFIs as a numbered list a reviewer can send.

## zones — `cad-analyze zones <file> [--tolerance 0.5]`

```jsonc
{ "zones": [ { "zone_id": "...", "area": 240.0, "label": "...", "...": "..." } ] }
```
Report: detected rooms/areas with their computed areas. Bump `--tolerance` if
loops aren't closing (units mismatch / small gaps).

## compare — `cad-revision diff <master> <revision> [--json]`

Separate CLI. Exit codes: `0` = no changes, `1` = changes found, `2` = error.
For applying approved changes, `cad-revision bundle <master> <revision> --output-dir <dir>`
writes a NEW master + overlay + changelog (original untouched).
