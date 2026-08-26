# 072 — Real-World User Profile Simulation System

> 25 AEC professionals, each with unique documents, workflows, and multi-turn conversations.
> Proves the platform works for the breadth of real-world users, not just one synthetic scenario.

**Document type:** TQ (Test/Quality)
**Epic:** EPIC-CAD-31
**Bead:** cad-dxf-agent-9i0
**Created:** 2026-03-09

## Overview

The existing E2E test suite uses the same `r2000_blocks.dxf` for all 15 conversations and 20 canary prompts. Real users upload wildly different drawings. This profile system simulates 25 different AEC professionals, each with their own documents, workflows, multi-turn conversations, and expected responses.

**Document variety:** 19 unique DXF files + 4 unique PDFs = 23 distinct documents. Profile 15 intentionally reuses the Profile 3 floor-plan fixture, and Profiles 12 and 18 intentionally reuse the sawcut plan, so the same drawings are exercised through distinct professional workflows.
**Format coverage:** 20 DXF uploads + 5 PDF uploads = 25% PDF coverage (vs current: 0%)

Each profile defines:
- **Who** the user is (role, experience, firm context)
- **What document** they upload (specific fixture file)
- **Why** they're using the platform (business deadline, deliverable, client need)
- **How** they interact (capabilities exercised, representative prompts, full conversation script)

---

## Profile-to-Fixture Mapping

| # | Profile | Document | Fixture Path | Format | Capabilities Tested |
|---|---------|----------|-------------|--------|-------------------|
| 1 | Structural Engineer (Sr) | Column layout | `tests/fixtures/revision/nasty/real_columns/master.dxf` | DXF | move, delete, health, summary |
| 2 | Structural Drafter | Bolt pattern sheet | `tests/fixtures/dxf_zoo/r2000_blocks.dxf` | DXF | move, edit_text, copy, Q&A |
| 3 | Architect (Residential) | Floor plan | `tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf` | DXF | zone, summary, compliance, add_text |
| 4 | Architect (Commercial) | Large detail set | `tests/fixtures/dxf_zoo/sourced/gds-api-cw750-details.dxf` | DXF | compliance, health, takeoff, summary |
| 5 | MEP Coordinator | Custom blocks | `tests/fixtures/dxf_zoo/sourced/jscad-CustomBlocks.dxf` | DXF | Q&A (equipment count), batch, add_block |
| 6 | Electrical Designer | Symbol blocks | `tests/fixtures/dxf_zoo/sourced/jscad-blocks1.dxf` | DXF | add_block, copy, batch, takeoff |
| 7 | Mechanical Engineer | Block layout | `tests/fixtures/dxf_zoo/sourced/jscad-blocks2.dxf` | DXF | move, rotate, scale, Q&A |
| 8 | Plumbing Designer | Piping lines | `tests/fixtures/dxf_zoo/sourced/jscad-2Dlines.dxf` | DXF | add_line, add_polyline, delete, Q&A |
| 9 | Fire Protection Eng. | Circle/arc layout | `tests/fixtures/dxf_zoo/sourced/jscad-2Dcircles.dxf` | DXF | add_circle, compliance, Q&A |
| 10 | GC Superintendent | Structural plan (PDF) | `tests/fixtures/test_pdfs/structural_plan.pdf` | PDF | summary, Q&A, health |
| 11 | Estimator | Foundation detail (PDF) | `tests/fixtures/test_pdfs/foundation_detail.pdf` | PDF | takeoff, Q&A, summary |
| 12 | Code Compliance Officer | Site plan (PDF) | `000-docs/032-TQ-TEST-sawcuts-sample-drawing.pdf` | PDF | compliance, RFI, health |
| 13 | Interior Designer | Text-heavy drawing | `tests/fixtures/dxf_zoo/sourced/jscad-texts.dxf` | DXF | edit_text, summary, zone, add_text |
| 14 | Civil Engineer | Polyline site plan | `tests/fixtures/dxf_zoo/sourced/jscad-2Dpolylines.dxf` | DXF | add_polyline, move, scale, Q&A |
| 15 | Landscape Designer (HeyFlora.ai) | Landscape site plan | `tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf` | DXF | compliance (MWELO), takeoff, summary, edit, Q&A, health |
| 16 | Construction Manager | Revision pair | `tests/fixtures/revision/clean_realworld/master.dxf` + `revision.dxf` | DXF | compare, summary, Q&A |
| 17 | Project Manager | Simple geometry (PDF) | `tests/fixtures/test_pdfs/simple_geometry.pdf` | PDF | summary, Q&A (non-technical) |
| 18 | Plan Reviewer (City) | Sawcut drawing (PDF) | `000-docs/032-TQ-TEST-sawcuts-sample-drawing.pdf` | PDF | compliance, RFI, health |
| 19 | Permit Expediter | R12 minimal drawing | `tests/fixtures/dxf_zoo/r12_basic.dxf` | DXF | summary, compliance, health, Q&A |
| 20 | Facility Manager | MText-heavy drawing | `tests/fixtures/dxf_zoo/sourced/gds-mtext-test.dxf` | DXF | Q&A, summary, edit_text, health |
| 21 | Shop Fabricator | Polyline details | `tests/fixtures/dxf_zoo/sourced/gds-polylines.dxf` | DXF | scale, mirror, Q&A, takeoff |
| 22 | Solar Installer | Rectangle layout | `tests/fixtures/dxf_zoo/sourced/jscad-2Drectangles.dxf` | DXF | add_block (panels), copy, batch, takeoff |
| 23 | BIM Coordinator | Modern polylines | `tests/fixtures/dxf_zoo/r2018_polylines.dxf` | DXF | health, compare, Q&A, summary |
| 24 | Junior Drafter/Intern | Layers + empty | `tests/fixtures/dxf_zoo/sourced/jscad-layers.dxf` | DXF | Q&A (learning), move, edit_text, summary |
| 25 | Landscape Field Crew Lead (HeyFlora.ai) | Arc/curve plan | `tests/fixtures/dxf_zoo/sourced/jscad-2Darcs.dxf` | DXF | Q&A, summary, health, takeoff |

---

## Capability Coverage Matrix

Verification that all platform capabilities appear in at least two profiles:

| Capability | Profiles |
|-----------|----------|
| summary | 1, 3, 4, 7, 8, 10, 11, 13, 14, 15, 16, 17, 19, 20, 23, 24, 25 |
| health | 1, 4, 9, 10, 12, 15, 18, 19, 20, 23, 25 |
| compliance | 3, 4, 9, 12, 15, 18, 19 |
| takeoff | 4, 5, 6, 11, 15, 21, 22, 25 |
| Q&A | 2, 5, 7, 8, 9, 10, 11, 14, 16, 17, 19, 20, 21, 22, 23, 24, 25 |
| RFI | 12, 18 |
| zone detection | 3, 13 |
| compare | 16, 23 |
| move | 1, 2, 7, 8, 14, 24 |
| delete | 1, 8 |
| edit_text | 2, 13, 20, 24 |
| add_text | 3, 13 |
| add_block | 5, 6, 22 |
| add_line | 8 |
| add_polyline | 8, 14 |
| add_circle | 9 |
| copy | 2, 6, 22 |
| rotate | 7 |
| scale | 7, 14, 21 |
| mirror | 21 |
| batch | 5, 6, 22 |

---

## Profiles

### Profile 01 — Senior Structural Engineer

**Who:** Maria Chen, PE, senior structural engineer at Chen & Associates (40-person structural firm). 15 years of experience. Currently reviewing a column layout for a 4-story commercial office building in downtown Portland.
**Document:** `tests/fixtures/revision/nasty/real_columns/master.dxf` (DXF)
**Business context:** Coordination deadline is tomorrow morning. The architect emailed asking Maria to verify column positions against the architectural grid before they issue the 90% CD set. She also needs to flag any drawing health issues before the file goes to the architect's BIM coordinator.

#### Capabilities exercised
- **summary** — quick overview of what's on the sheet before diving in
- **health** — catch drawing quality issues (duplicate entities, missing layers, orphaned blocks) before sending to architect
- **move** — reposition a column that's 6 inches off the architectural grid
- **delete** — remove a temporary construction note that shouldn't be in the issued set

#### Representative prompts
1. "Give me a summary of this drawing"
2. "Run a health check on this file"
3. "Move the column at grid B-3 six inches to the north"
4. "Delete the text note that says TEMP SHORING"
5. "How many columns are on layer S-COLS?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Summarize this drawing — I need to know what we're working with before the coordination meeting" | summary | Returns structured summary: entity counts by type and layer, block references, spatial extents. Identifies this as a structural column layout with grid lines. |
| 2 | "Check the health of this file. The architect's BIM coordinator is picky about clean deliverables" | health | Returns health report: flags duplicate entities, zero-length lines, empty text, layer naming inconsistencies, orphaned blocks. Assigns overall quality score. |
| 3 | "The column at B-3 is 6 inches off the arch grid. Move it 6 inches north" | edit_plan | Generates move operation targeting the INSERT entity at the B-3 grid intersection. Validates the move vector. Preview shows old and new position. |
| 4 | "Looks good. Now delete the note that says TEMP SHORING — that was for the contractor, shouldn't be in the CD set" | edit_plan | Finds TEXT/MTEXT entity containing "TEMP SHORING". Generates delete operation. Confirms the entity isn't on a protected layer before removing. |

---

### Profile 02 — Structural Drafter

**Who:** Kevin Park, CAD drafter at Chen & Associates (same firm as Maria). 3 years of experience, works primarily on shop drawings and detail sheets. Currently cleaning up bolt pattern annotations on a steel connection shop drawing.
**Document:** `tests/fixtures/dxf_zoo/r2000_blocks.dxf` (DXF)
**Business context:** The shop drawing package is due to the steel fabricator by Friday. Kevin needs to fix bolt mark labels that got garbled during an AutoCAD version conversion, and copy a bolt pattern to three new grid locations.

#### Capabilities exercised
- **Q&A** — understand the bolt layout and block organization
- **edit_text** — fix garbled bolt mark labels
- **copy** — duplicate bolt patterns to new grid locations
- **move** — fine-tune bolt position after copying

#### Representative prompts
1. "How many bolt blocks are in this drawing?"
2. "What does the text next to the top-left bolt group say?"
3. "Change the text 'BM-A1' to 'BM-C3'"
4. "Copy the bolt group at the top-left corner to coordinates 120,45"
5. "Move that copied group 2 inches to the right"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "How many blocks are in this drawing and what are they named?" | qna | Queries the drawing context for all INSERT entities. Returns block names and counts. Lists unique block definitions. |
| 2 | "The label next to the first bolt group says BM-A1 but it should say BM-C3. Fix that" | edit_plan | Finds TEXT entity containing "BM-A1". Generates edit_text operation changing content to "BM-C3". Preview shows before/after text. |
| 3 | "Copy the block at 10,10 to 120,45" | edit_plan | Generates copy operation targeting the INSERT entity nearest to (10,10). New position at (120,45). Validates target coordinates are within drawing extents. |
| 4 | "That's close but nudge it 2 inches to the right" | edit_plan | Context-aware follow-up: recognizes "it" refers to the just-copied block. Generates move operation with delta X=2, delta Y=0. |

---

### Profile 03 — Residential Architect

**Who:** Sarah Kim, sole practitioner at SKim Architecture. Licensed architect with 8 years of experience, specializing in residential remodels and ADUs in the San Francisco Bay Area. Currently designing a kitchen remodel for a homeowner.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf` (DXF)
**Business context:** Client meeting in 2 days. Sarah needs to verify the floor plan zones make sense, run a quick code compliance check for egress widths (California residential code), add room labels the client can read, and generate a plain-English summary for the homeowner who doesn't read drawings.

#### Capabilities exercised
- **summary** — plain-English overview for the homeowner client
- **zone detection** — identify rooms and calculate areas
- **compliance** — check egress widths and clearances
- **add_text** — add room labels

#### Representative prompts
1. "Can you summarize what this floor plan shows? I need to explain it to my client who doesn't read drawings"
2. "Detect the rooms in this plan and tell me their areas"
3. "Check if the hallway widths and door clearances meet California residential code"
4. "Add a text label 'KITCHEN' at 15,20"
5. "What's the total square footage of the living areas?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Summarize this floor plan in plain English — my client is a homeowner, not a builder" | summary | Returns narrative summary in non-technical language. Describes room layout, approximate sizes, flow between spaces. Avoids jargon. |
| 2 | "Detect the rooms and zones in this plan. What are the areas?" | zone_detection | Runs closed-loop zone detection. Identifies enclosed areas from polyline boundaries. Calculates area for each detected zone. Returns zone list with coordinates and square footage. |
| 3 | "Do the corridors and door openings comply with California residential building code?" | compliance | Runs compliance check against residential egress requirements. Checks minimum corridor width (36"), door clear width (32"), and clearances. Reports findings with code references. |
| 4 | "Add a label that says 'KITCHEN' centered at coordinates 15,20" | edit_plan | Generates add_text operation with content "KITCHEN" at position (15,20). Places on appropriate annotation layer. Preview shows text placement in context. |

---

### Profile 04 — Commercial Architect

**Who:** David Rodriguez, AIA, project architect at Meridian Design Group (200-person firm). 12 years of experience, currently leading the construction documents phase for a hospital wing addition in Austin, TX.
**Document:** `tests/fixtures/dxf_zoo/sourced/gds-api-cw750-details.dxf` (DXF)
**Business context:** The 60% CD submittal to the hospital system is next Wednesday. David needs to audit drawing health across the detail set, verify ADA and IBC compliance for the curtain wall details, run a material takeoff for the curtain wall system, and generate a summary for the client progress report.

#### Capabilities exercised
- **summary** — drawing overview for client report
- **compliance** — ADA/IBC checks on curtain wall details
- **health** — drawing quality audit before submittal
- **takeoff** — material quantities for curtain wall system

#### Representative prompts
1. "Generate a summary of this detail sheet for our client progress report"
2. "Check these details against ADA accessibility requirements"
3. "Run a health report — we're submitting to the hospital next week and I don't want embarrassing errors"
4. "Give me a material takeoff of the curtain wall components"
5. "How many unique detail callouts are on this sheet?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Summarize this detail sheet. I need a paragraph for our 60% CD progress report to the client" | summary | Returns structured summary identifying the sheet as curtain wall construction details. Lists detail types, materials referenced, and scope. Written at a level appropriate for a client report. |
| 2 | "Check compliance with ADA and IBC — this is a hospital so accessibility is critical" | compliance | Runs compliance engine against ADA and IBC requirements. Checks dimensions against accessibility standards. Flags any findings with code section references and severity levels. |
| 3 | "Run health check. Last time we submitted, the hospital's plan reviewer sent back a list of drawing errors and it was embarrassing" | health | Deep health audit: checks for duplicate entities, zero-length geometry, text overlaps, layer standard compliance, missing annotations. Returns scored report with specific issues and locations. |
| 4 | "Takeoff the curtain wall components — I need quantities for the cost consultant" | takeoff | Extracts quantities by entity type and layer. Groups by material/component type. Returns structured takeoff with counts, lengths, and areas where applicable. |

---

### Profile 05 — MEP Coordinator

**Who:** James Wu, MEP coordinator at Pacific Mechanical Contractors. 7 years of experience coordinating mechanical, electrical, and plumbing trades for commercial projects. Currently coordinating equipment placement for a data center build-out.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-CustomBlocks.dxf` (DXF)
**Business context:** Clash detection meeting with the GC and other trades in 3 days. James needs to count all equipment blocks, verify their positions relative to structural clearances, and add a missing CRAC unit block before the coordination model gets updated.

#### Capabilities exercised
- **Q&A** — equipment counts and block identification
- **batch** — repositioning multiple equipment blocks
- **add_block** — inserting missing equipment

#### Representative prompts
1. "How many equipment blocks are in this drawing?"
2. "What are the names of all the block definitions?"
3. "What block is closest to coordinate 50,30?"
4. "Add a block named 'CRAC-UNIT' at position 80,60"
5. "Move all blocks on the MECH-EQUIP layer 12 inches south"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Count all equipment blocks. I need to reconcile against the equipment schedule before the clash meeting" | qna | Queries all INSERT entities. Returns count per block name. Lists unique block definitions with instance counts. |
| 2 | "What are the block names and how many of each?" | qna | Follow-up: provides detailed breakdown of block definitions and their insertion counts, positions, and layers. |
| 3 | "Add a CRAC unit — use block name 'CRAC-UNIT' and put it at 80,60 on the MECH-EQUIP layer" | edit_plan | Generates add_block operation. Block name "CRAC-UNIT", position (80,60), layer "MECH-EQUIP". Validates the block definition exists or notes it will be created. |
| 4 | "Actually, we need to shift that CRAC unit 24 inches east. The structural column is in the way" | edit_plan | Context-aware follow-up: targets the just-added block. Generates move operation with delta X=24, delta Y=0. Preview confirms new position clears the column. |

---

### Profile 06 — Electrical Designer

**Who:** Lisa Chang, electrical designer at Volta Engineering. 5 years of experience designing power distribution for commercial and institutional projects. Currently laying out panel schedules and circuit routing for a new middle school.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-blocks1.dxf` (DXF)
**Business context:** Electrical permit drawings are due to the school district next week. Lisa needs to add panel symbols to classrooms that are missing them, copy standard circuit blocks to new locations, and run a symbol takeoff for the electrical spec.

#### Capabilities exercised
- **add_block** — inserting panel symbols
- **copy** — duplicating circuit blocks
- **batch** — adding symbols to multiple rooms
- **takeoff** — counting all electrical symbols

#### Representative prompts
1. "What kinds of symbol blocks are in this drawing?"
2. "Add a panel symbol block at 35,22"
3. "Copy the block at 35,22 to 55,22 and 75,22"
4. "How many total panel symbols are there now?"
5. "Give me a takeoff of all electrical symbols by type"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "List all the block types in this drawing. I need to know what symbols are already placed" | qna | Returns all unique block definitions with counts. Identifies symbol types based on block naming conventions. |
| 2 | "I need to add a panel symbol at 35,22 on the ELEC-PANEL layer" | edit_plan | Generates add_block operation with specified block name, position, and layer. Preview shows placement location. |
| 3 | "Copy that panel to 55,22 and 75,22 — those classrooms need panels too" | edit_plan | Generates two copy operations from the source at (35,22) to both target locations. Maintains same layer assignment. |
| 4 | "Run a takeoff of all the electrical symbols so I can cross-check with the panel schedule" | takeoff | Extracts all INSERT entities on electrical layers. Groups by block name. Returns structured count with positions. Suitable for cross-referencing against the panel schedule. |

---

### Profile 07 — Mechanical Engineer

**Who:** Robert Singh, PE, mechanical engineer at AirTech Consulting. 10 years of experience in HVAC design for commercial buildings. Currently reviewing the mechanical equipment layout for a 3-story medical office building.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-blocks2.dxf` (DXF)
**Business context:** Design development review meeting with the architect on Thursday. Robert needs to reposition an AHU that conflicts with the structural framing, rotate a condenser unit for better service access, and verify clearances are maintained.

#### Capabilities exercised
- **move** — repositioning equipment
- **rotate** — rotating equipment for access
- **scale** — adjusting equipment representation size
- **Q&A** — verifying clearances and positions

#### Representative prompts
1. "Where is the largest block in this drawing?"
2. "Move it 36 inches to the east"
3. "Rotate the block at 40,50 by 90 degrees"
4. "What's the distance between the block at 40,50 and the nearest wall line?"
5. "Give me a summary of all equipment positions"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Where are all the equipment blocks and what are their positions?" | qna | Returns list of all INSERT entities with block name, position coordinates, and layer. Sorted by position or grouped logically. |
| 2 | "The AHU block needs to move 36 inches east — the beam is in the way" | edit_plan | Identifies the AHU block from context. Generates move operation with delta X=36, delta Y=0. Preview shows clearance from structural elements. |
| 3 | "Rotate the condenser at 40,50 ninety degrees counterclockwise so the service panel faces the access corridor" | edit_plan | Generates rotate operation targeting the INSERT at (40,50). Rotation angle 90 degrees CCW. Preview shows new orientation. |
| 4 | "Now check — is there at least 36 inches of clearance around that condenser for service access?" | qna | Spatial query: finds nearest entities to the rotated block. Calculates distances. Reports whether 36-inch clearance is maintained on all sides. |

---

### Profile 08 — Plumbing Designer

**Who:** Amanda Torres, plumbing designer at FlowState MEP. 4 years of experience routing domestic water and waste lines for commercial kitchens and restaurants. Currently designing the waste line routing for a new restaurant tenant improvement.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-2Dlines.dxf` (DXF)
**Business context:** Plumbing rough-in package due to the GC next week. Amanda needs to add new pipe runs, delete abandoned waste lines from a previous design iteration, and verify all connections terminate correctly.

#### Capabilities exercised
- **add_line** — new pipe runs
- **add_polyline** — multi-segment pipe routes
- **delete** — removing abandoned lines
- **Q&A** — verifying connections

#### Representative prompts
1. "How many line entities are in this drawing?"
2. "What layers have line entities?"
3. "Add a line from 10,20 to 50,20 on the PLMB-WASTE layer"
4. "Delete the line closest to 30,15"
5. "Are there any lines that don't connect to anything?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "How many lines are in this drawing and what layers are they on?" | qna | Counts all LINE entities. Groups by layer. Returns layer-by-layer breakdown with entity counts. |
| 2 | "Add a waste line from 10,20 to 50,20 on the PLMB-WASTE layer" | edit_plan | Generates add_line operation with start (10,20), end (50,20), layer "PLMB-WASTE". Preview shows the new line in context. |
| 3 | "Delete the line closest to coordinate 30,15 — that's an old route we abandoned" | edit_plan | Uses spatial query to find the LINE entity nearest to (30,15). Generates delete operation. Confirms the entity isn't on a protected layer. |
| 4 | "Are there any dead-end lines that don't connect to other lines? I want to make sure I didn't leave any orphans" | qna | Analyzes line connectivity: checks line endpoints for proximity to other line endpoints. Reports any lines with endpoints that don't connect (within tolerance) to other geometry. |

---

### Profile 09 — Fire Protection Engineer

**Who:** Michael Brown, PE, fire protection engineer at FireSafe Consulting. 9 years of experience designing fire sprinkler systems. Currently reviewing sprinkler head layout for a 20,000 SF open office floor.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-2Dcircles.dxf` (DXF)
**Business context:** Fire marshal plan review submission next week. Michael needs to verify sprinkler head spacing meets NFPA 13 requirements for ordinary hazard occupancy, add heads in coverage gaps, and generate a compliance report for the submittal package.

#### Capabilities exercised
- **add_circle** — adding sprinkler head coverage areas
- **compliance** — NFPA 13 spacing verification
- **Q&A** — coverage area and head count queries

#### Representative prompts
1. "How many circles are in this drawing?"
2. "What's the average spacing between circle centers?"
3. "Check if the spacing between heads meets NFPA 13 ordinary hazard requirements"
4. "Add a circle with radius 7.5 at position 45,30"
5. "Run a health check — are any circles overlapping excessively?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Count the sprinkler heads. Each circle represents a coverage area" | qna | Counts all CIRCLE entities. Returns total count and lists positions. Notes the radii for coverage area verification. |
| 2 | "Check compliance — NFPA 13 says ordinary hazard heads need to be no more than 15 feet apart and each head covers max 130 square feet" | compliance | Runs compliance check with specified parameters. Measures center-to-center distances between circles. Flags any pairs exceeding 15-foot spacing. Checks coverage area per head against 130 SF limit. |
| 3 | "There's a gap in coverage near 45,30. Add a sprinkler head there — radius 7.5 to match the others" | edit_plan | Generates add_circle operation at (45,30) with radius 7.5. Places on the same layer as existing circles. Preview shows the new head relative to adjacent heads. |
| 4 | "Now re-check — does the new layout pass NFPA 13 spacing?" | compliance | Re-runs compliance including the newly added circle. Reports pass/fail on all spacing criteria. Confirms the gap at 45,30 is resolved. |

---

### Profile 10 — GC Superintendent

**Who:** Tom Williams, superintendent at BuildRight Construction, overseeing a 50-unit multifamily project in Boise, ID. 20 years in the field. Reviews drawings on his iPad at the job site trailer. Not a CAD user — needs plain-English answers.
**Document:** `tests/fixtures/test_pdfs/structural_plan.pdf` (PDF)
**Business context:** Concrete pour scheduled for Thursday. Tom got the structural plans from the engineer this morning and needs to quickly understand what's on the sheet, verify footing callouts match what was discussed in the last coordination meeting, and flag anything that looks wrong before the pour.

#### Capabilities exercised
- **summary** — plain-English overview of the structural plan
- **Q&A** — questions about footings, rebar, and callouts
- **health** — flag potential drawing issues

#### Representative prompts
1. "What's on this sheet?"
2. "What size are the footings called out?"
3. "What rebar is specified for the grade beams?"
4. "Anything look off on this drawing?"
5. "Can you tell if there's a note about the concrete strength?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Just tell me what's on this sheet. I'm a super, not an engineer" | summary | Returns plain-English summary of the PDF. Identifies it as a structural foundation plan. Describes footing types, grade beams, and callouts in non-technical language. |
| 2 | "What size footings are we looking at? I need to check against what we excavated" | qna | Extracts footing dimension callouts from the PDF. Reports sizes (width x depth) for each footing type. Presented in field-friendly terms. |
| 3 | "What about rebar? What's the engineer calling for in the grade beams?" | qna | Extracts rebar specifications from the drawing notes and callouts. Reports bar sizes, spacing, and any special requirements. |
| 4 | "Anything look wrong or unusual? I don't want any surprises on pour day" | health | Runs health/quality check on the PDF. Flags any missing callouts, inconsistent dimensions, unclear notes, or potential conflicts. Reports in plain English. |

---

### Profile 11 — Estimator

**Who:** Rachel Garcia, senior estimator at Apex General Contractors. 12 years of estimating experience across commercial and institutional projects. Currently bidding a strip mall foundation package.
**Document:** `tests/fixtures/test_pdfs/foundation_detail.pdf` (PDF)
**Business context:** Bid due in 48 hours. Rachel needs to extract concrete and rebar quantities from the foundation detail to plug into her estimate. Every cubic yard and pound of rebar matters for the bid price.

#### Capabilities exercised
- **takeoff** — extract material quantities
- **Q&A** — concrete volume and rebar spec questions
- **summary** — overview of what's being detailed

#### Representative prompts
1. "Summarize this foundation detail"
2. "Give me a material takeoff — I need concrete volumes and rebar weights"
3. "What's the concrete strength spec?"
4. "How many linear feet of grade beam are shown?"
5. "Are there any dowel callouts I should include in the rebar count?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "What am I looking at here? Give me a quick summary" | summary | Identifies the PDF as a foundation detail. Describes the footing type, grade beam configuration, and key dimensions. Notes any specifications or general notes visible. |
| 2 | "Run a takeoff. I need quantities for my bid — concrete volume, rebar weight, formwork area, whatever you can extract" | takeoff | Extracts quantities from the detail: concrete volume (cubic yards), rebar quantities by size, formwork contact area, and any other quantifiable items. Structured for direct use in a cost estimate. |
| 3 | "What's the concrete strength called out? I need to price the right mix" | qna | Searches the drawing notes and callouts for concrete compressive strength specification (e.g., 3000 PSI, 4000 PSI). Reports the spec with the location where it was found. |
| 4 | "Any dowels or special rebar callouts I might miss if I'm rushing?" | qna | Searches for dowel callouts, special rebar details, lap splice notes, or other rebar-related specifications that could be overlooked. Reports findings with locations. |

---

### Profile 12 — Code Compliance Officer

**Who:** Officer Patricia Nelson, senior plan reviewer at the City of Mulberry Building Department. 18 years of plan review experience. Processes 15-20 permit applications per week across residential and commercial projects.
**Document:** `000-docs/032-TQ-TEST-sawcuts-sample-drawing.pdf` (PDF)
**Business context:** The plan review queue is backed up. Patricia needs to quickly check submitted plans for code compliance, flag deficiencies, and generate RFIs (Requests for Information) for anything that doesn't meet code. Her department has a 10-business-day turnaround requirement.

#### Capabilities exercised
- **compliance** — code compliance check against building standards
- **RFI** — automated RFI generation for deficiencies
- **health** — drawing quality issues that affect reviewability

#### Representative prompts
1. "Check this submittal for building code compliance"
2. "Generate RFIs for every code deficiency you found"
3. "Are the emergency egress paths clearly marked and compliant?"
4. "Check if the site plan shows required setbacks"
5. "Rate the overall quality of this submittal — is it reviewer-friendly?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Run a compliance check on this permit submittal. I need to know what doesn't meet code" | compliance | Comprehensive code compliance scan. Checks against IBC, ADA, and local amendments. Reports findings with severity (violation, warning, advisory), code section references, and locations on the drawing. |
| 2 | "Generate RFIs for each deficiency. Format them so I can send directly to the applicant" | rfi | Converts each compliance finding into a formal RFI. Each RFI includes: item number, drawing reference, deficiency description, applicable code section, and required response. Formatted for official correspondence. |
| 3 | "Check the health of this drawing set — is it professional quality or am I going to struggle reading it?" | health | Evaluates drawing quality from a plan reviewer's perspective: legibility, completeness of annotations, scale consistency, title block information, sheet organization. Reports issues that would slow down review. |
| 4 | "Is there a fire separation wall shown between the occupancy groups?" | qna | Searches the drawing for fire separation indicators: rated wall symbols, fire rating annotations, area separation notations. Reports what was found and whether it appears adequate for the occupancy types shown. |

---

### Profile 13 — Interior Designer

**Who:** Nicole Foster, principal at Foster Interiors, specializing in restaurant and hospitality design. 10 years of experience. Currently working on a tenant improvement for a farm-to-table restaurant in a historic building.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-texts.dxf` (DXF)
**Business context:** Client presentation tomorrow afternoon. Nicole needs to update finish schedule notes that reference the wrong materials, add room labels for the client's benefit, and generate a summary she can paste into her presentation slides. The historic building means careful attention to existing conditions notes.

#### Capabilities exercised
- **edit_text** — updating finish schedule annotations
- **add_text** — adding room labels
- **summary** — overview for client presentation
- **zone detection** — identifying rooms/spaces

#### Representative prompts
1. "Summarize this drawing for me"
2. "Find all text that mentions 'carpet' — the client changed to hardwood"
3. "Change 'CARPET TYPE 1' to 'WHITE OAK HARDWOOD'"
4. "Add a label 'MAIN DINING' at position 25,35"
5. "Detect the rooms in this plan"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Give me a quick summary — I need to brief the client on what this sheet covers" | summary | Returns summary identifying the drawing content, text annotations present, and overall organization. Notes any finish schedule or material references in the text entities. |
| 2 | "The client decided against carpet. Change every instance of 'CARPET TYPE 1' to 'WHITE OAK HARDWOOD'" | edit_plan | Finds all TEXT/MTEXT entities containing "CARPET TYPE 1". Generates edit_text operations for each instance. Preview shows all changes in context. Handles batch text replacement. |
| 3 | "Add a label 'MAIN DINING' at 25,35 and 'BAR LOUNGE' at 40,35" | edit_plan | Generates two add_text operations. First: "MAIN DINING" at (25,35). Second: "BAR LOUNGE" at (40,35). Both on an annotation layer. |
| 4 | "Can you detect the different rooms or zones? I want to make sure every space has a label" | zone_detection | Runs zone detection to identify enclosed areas. Returns detected zones with boundaries and areas. Helps Nicole identify which spaces still need labels. |

---

### Profile 14 — Civil Engineer

**Who:** Carlos Mendez, PE, civil engineer at TerraSite Engineering. 11 years of experience in site design, grading, and drainage for commercial and industrial projects. Currently designing a 200-stall parking lot for a retail center.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-2Dpolylines.dxf` (DXF)
**Business context:** Grading permit submittal to the city is next Tuesday. Carlos needs to add drainage polylines showing flow paths, adjust the parking lot boundary for a design change, scale a detail inset, and verify slope callouts.

#### Capabilities exercised
- **add_polyline** — drainage flow lines
- **move** — adjusting boundary geometry
- **scale** — resizing detail insets
- **Q&A** — dimension and slope verification

#### Representative prompts
1. "How many polylines are in this drawing?"
2. "What layers have polyline entities?"
3. "Add a polyline from 0,0 to 20,0 to 20,30 to 0,30 on the CIVIL-DRAIN layer"
4. "Move the polyline closest to 50,50 about 10 feet north"
5. "Scale the polyline at 80,80 by a factor of 1.5"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "How many polylines are in the drawing and what layers are they on?" | qna | Counts all LWPOLYLINE entities. Groups by layer. Returns per-layer counts and total. Notes any polylines with significant vertex counts. |
| 2 | "Add a drainage path — polyline from 10,0 to 30,0 to 30,20 to 50,20 on the CIVIL-DRAIN layer" | edit_plan | Generates add_polyline operation with four vertices at the specified coordinates. Layer "CIVIL-DRAIN". Preview shows the new polyline in context. |
| 3 | "The architect shifted the building pad. Move the polyline nearest to 50,50 ten feet to the north" | edit_plan | Spatial query finds the LWPOLYLINE nearest to (50,50). Generates move operation with delta Y=10 (assuming 1 unit = 1 foot). Preview shows new position. |
| 4 | "Scale that detail inset at 80,80 by 1.5 — the city reviewer asked for it bigger" | edit_plan | Finds entity at (80,80). Generates scale operation with factor 1.5 about the base point. Preview shows before/after size comparison. |

---

### Profile 15 — Landscape Designer (HeyFlora.ai workflow)

**Who:** Maya Greenfield, RLA (Registered Landscape Architect) at GreenEdge Design-Build, specializing in water-efficient landscape design. 9 years of experience in drought-tolerant commercial landscapes in Southern California. Currently designing a 2-acre water-efficient landscape for a new corporate campus in Irvine.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf` (DXF)
**Business context:** Client proposal due next week. Maya needs to verify the planting plan complies with California's Model Water Efficient Landscape Ordinance (MWELO), count all plant symbols for the bid, generate a client-facing summary for the proposal document, and adjust planting group spacing to optimize irrigation coverage.

#### Capabilities exercised
- **summary** — client-facing proposal narrative
- **compliance** — MWELO water-efficiency verification
- **takeoff** — plant counts and material quantities
- **move** — adjust planting group spacing
- **Q&A** — irrigation zone and plant identification queries
- **health** — drawing quality before client delivery

#### Representative prompts
1. "Generate a summary I can paste into the client proposal — describe the landscape design intent and scope"
2. "Check if this planting plan complies with California MWELO requirements"
3. "Count all plant symbols and group by species type for the bid"
4. "Move the planting group near 25,40 about 3 feet east to improve sprinkler coverage"
5. "What irrigation zones are shown and what's in each zone?"
6. "Run a health check before I send this to the client"

#### Conversation script (5 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "I need a summary for the client proposal. Describe the design — planting areas, hardscape, irrigation zones. Make it sound professional but not overly technical" | summary | Returns a polished narrative summary suitable for a landscape architecture proposal. Describes spatial organization, planting areas, and design features in client-friendly language. |
| 2 | "Check MWELO compliance. California requires a Maximum Applied Water Allowance based on the landscape area and an ET adjustment factor. Flag anything that might not pass" | compliance | Runs compliance check against MWELO framework. Evaluates planting area ratios, plant water use classifications (if detectable), and irrigation system indicators. Reports findings with MWELO section references. |
| 3 | "Takeoff all plant symbols. I need a count by type for the bid quantities" | takeoff | Extracts all INSERT entities representing plant symbols. Groups by block name/type. Returns a structured plant schedule with counts, suitable for bid pricing. |
| 4 | "The irrigation designer said the group near 25,40 needs to shift 3 feet east for better head-to-head coverage. Move it" | edit_plan | Targets entities near (25,40). Generates move operation with delta X=3. Preview confirms new position improves spacing relative to adjacent groups. |
| 5 | "Great. Now give me an updated summary I can paste into the proposal reflecting the changes we made" | summary | Generates an updated summary that accounts for the modifications made during this session. Notes the adjusted planting positions and any compliance improvements. |

#### Landscape management integration context

This profile models a HeyFlora.ai landscape-design workflow in the landscape management vertical — a $150B professional sector that relies on drawing analysis for compliance, bidding, and field operations. Landscape design firms need to:
- Read DXF/PDF site plans and extract plant counts for bid pricing
- Check spatial compliance against water-efficiency ordinances (MWELO, LEED)
- Generate client-facing summaries for proposals and reports

**Compliance frameworks checked:**
- **MWELO** (Model Water Efficient Landscape Ordinance) — California water use requirements for new landscapes
- **LEED Sustainable Sites** — Credits SS-5.1 (site development, protect/restore habitat) and WE-1 (water-efficient landscaping)
- **ANSI A300** — Tree care standard (relevant when existing trees are on the plan)

---

### Profile 16 — Construction Manager

**Who:** Steve O'Brien, construction manager at NationalBuild CM, overseeing a $45M university science building. 16 years of CM experience. Manages architect/contractor coordination and tracks revisions across disciplines.
**Document:** `tests/fixtures/revision/clean_realworld/master.dxf` + `revision.dxf` (DXF pair)
**Business context:** The architect issued a revision yesterday. Steve needs to compare the new issue against the previous one, understand exactly what changed, and brief the project team at the weekly coordination meeting. He needs to know if the changes affect the construction schedule.

#### Capabilities exercised
- **summary** — overview of the master drawing
- **compare** — diff between master and revision
- **Q&A** — questions about specific changes

#### Representative prompts
1. "Summarize this drawing"
2. "Compare this with the revision"
3. "What specifically changed between the two versions?"
4. "Did any structural elements move?"
5. "Give me a summary of the differences I can share with the team"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Summarize the master drawing so I have context before looking at the revision" | summary | Returns structured summary of the master DXF: entity counts, layers, spatial extents, key features identified. |
| 2 | "Now compare it with the revision. What changed?" | compare | Runs the comparison engine against both DXF files. Alignment, entity matching, and change detection. Returns a structured changelog: additions, deletions, modifications with locations. |
| 3 | "Did anything structural move? That's what would affect my schedule" | qna | Context-aware follow-up on the comparison results. Filters changes to structural layers/entities. Reports whether any structural elements were added, removed, or repositioned. |
| 4 | "Give me a one-paragraph summary of the changes I can email to the project team" | summary | Synthesizes the comparison results into a concise narrative paragraph. Highlights the most significant changes, their locations, and potential impact. Written for a non-technical project team audience. |

---

### Profile 17 — Project Manager

**Who:** Jennifer Hayes, VP of Development at Harbor Realty Partners. MBA, not an engineer. Reviews drawings to understand project status for the board and investors. Currently overseeing a mixed-use development in Nashville.
**Document:** `tests/fixtures/test_pdfs/simple_geometry.pdf` (PDF)
**Business context:** Board presentation on Friday. Jennifer received contractor submittals and needs to understand what the drawings show so she can prepare talking points. She asks non-technical questions and needs plain-English answers without jargon.

#### Capabilities exercised
- **summary** — plain-English overview for a non-technical audience
- **Q&A** — simple questions about what's shown

#### Representative prompts
1. "What is this drawing showing?"
2. "Explain this to me like I'm not an engineer"
3. "How many rooms or spaces are shown?"
4. "What materials are called out?"
5. "Is there anything on this drawing I should be concerned about?"

#### Conversation script (3 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "I got this from the contractor. Can you tell me what it is and what it shows? I'm not technical" | summary | Returns a plain-English summary with zero jargon. Describes what's shown in terms a business professional would understand. Uses analogies where helpful. |
| 2 | "What are the key things I should know about for the board meeting?" | qna | Identifies the most significant items on the drawing from a project oversight perspective: scope, scale, major components. Frames answers in terms of project milestones and budget implications. |
| 3 | "Is there anything that looks unusual or that I should ask the contractor about?" | qna | Reviews the drawing for notable items, potential issues, or missing information. Frames findings as questions Jennifer can ask the contractor, rather than technical assessments. |

---

### Profile 18 — Plan Reviewer (City)

**Who:** Inspector Ray Kowalski, senior plan reviewer at the City of Springfield Public Works Department. 22 years of experience reviewing civil engineering plans for municipal permits. Specializes in utility and right-of-way work.
**Document:** `000-docs/032-TQ-TEST-sawcuts-sample-drawing.pdf` (PDF)
**Business context:** Processing a backlog of utility permit applications. Ray needs to check sawcut and utility connection drawings against municipal standards, generate RFIs for non-compliant elements, and maintain consistent review quality despite the volume.

#### Capabilities exercised
- **compliance** — municipal standards verification
- **RFI** — automated RFI generation
- **health** — drawing quality assessment
- **Q&A** — specific technical queries

#### Representative prompts
1. "Check this sawcut drawing against city utility standards"
2. "Generate RFIs for anything that doesn't meet our standards"
3. "Are the utility connection details shown correctly?"
4. "Rate the drawing quality — can my inspectors read this in the field?"
5. "Are there trench cross-section details?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Run compliance against our municipal utility standards. I need to know if the sawcut specs, trench details, and backfill requirements are shown correctly" | compliance | Checks the drawing against standard municipal requirements for utility work: sawcut widths, trench dimensions, backfill specifications, traffic control notes. Reports findings with standard references. |
| 2 | "Generate RFIs for the deficiencies. Standard format — I'll send them to the applicant through our permit portal" | rfi | Converts each compliance finding into a formal RFI. Includes: RFI number, sheet reference, deficiency description, applicable municipal standard, and required corrective action. |
| 3 | "How's the overall drawing quality? My field inspectors need to be able to read these at the trench" | health | Evaluates drawing quality for field use: text legibility, dimension clarity, detail completeness, scale appropriateness. Notes any issues that would make field inspection difficult. |
| 4 | "Is there a note about the pavement restoration requirement? We need to see T-cut specs" | qna | Searches the drawing for pavement restoration notes, T-cut specifications, and related details. Reports what was found and whether it meets the standard requirement. |

---

### Profile 19 — Permit Expediter

**Who:** Danielle Cho, permit expediter at FastTrack Consulting. 6 years of experience navigating the permit process for developers and architects across multiple jurisdictions. Currently processing entitlements for a 12-unit townhouse development.
**Document:** `tests/fixtures/dxf_zoo/r12_basic.dxf` (DXF)
**Business context:** Permit application deadline is tomorrow. The architect sent Danielle an older DXF file (R12 format) and she needs to verify it meets minimum submittal requirements before uploading to the city's plan review portal. She's not a drafter — she just needs to know if the file is acceptable.

#### Capabilities exercised
- **summary** — what's in the file
- **compliance** — minimum submittal requirements
- **health** — file format and quality issues
- **Q&A** — completeness questions

#### Representative prompts
1. "What's in this file? I need to know if it's the right drawing before I upload it"
2. "Will the city accept this? Check it against standard submittal requirements"
3. "Run a health check — is the file quality okay?"
4. "Does it have a title block and sheet number?"
5. "Is this an old file format? Will that cause problems?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Summarize this drawing. I need to verify it's the right file before I submit it to the city" | summary | Returns summary noting the DXF version (R12), entity types present, layers, and general content description. Flags the older format as notable. |
| 2 | "The city requires a title block, north arrow, scale notation, and sheet number. Does this drawing have those?" | compliance | Checks for the presence of standard submittal elements: title block (searches for TITLEBLOCK layer or known block names), north arrow symbol, scale text, and sheet numbering. Reports what's present and what's missing. |
| 3 | "Run a health check. I don't want the city to reject it for technical issues" | health | Evaluates file quality: DXF version compatibility, entity integrity, layer organization, text legibility. Flags R12-specific issues like limited entity type support. |
| 4 | "This is an R12 file — is that going to cause problems with modern plan review software?" | qna | Explains R12 format limitations: no MTEXT support, limited block attributes, potential compatibility issues with modern viewers. Recommends whether a format conversion would be advisable. |

---

### Profile 20 — Facility Manager

**Who:** George Patterson, Director of Facilities at Pacific State University. 15 years managing a 45-building campus. Responsible for maintaining as-built records, coordinating renovations, and annual facility audits.
**Document:** `tests/fixtures/dxf_zoo/sourced/gds-mtext-test.dxf` (DXF)
**Business context:** Annual facility audit season. George is updating maintenance records on building floor plans — changing dates, updating equipment notes, and checking that the drawing quality is adequate for the facility management database.

#### Capabilities exercised
- **Q&A** — reading existing maintenance notes
- **summary** — overview of the drawing contents
- **edit_text** — updating dates and notes
- **health** — drawing quality for archival

#### Representative prompts
1. "What notes are on this drawing?"
2. "Summarize the drawing contents"
3. "Change the date '2024-01-15' to '2026-03-09' wherever it appears"
4. "Run a health check — this needs to be clean for our records"
5. "Are there any maintenance schedule notes?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "List all the text notes on this drawing. I need to see what maintenance records are documented here" | qna | Extracts all TEXT and MTEXT entities. Returns the text content, positions, and layers. Groups by type (MTEXT vs TEXT) since this is an MTEXT-heavy drawing. |
| 2 | "Give me an overall summary — what does this drawing cover?" | summary | Returns summary describing the drawing content, noting the heavy use of MTEXT annotations. Identifies any patterns in the text content (dates, equipment references, maintenance notes). |
| 3 | "Update all dates that say '2024-01-15' to today's date, '2026-03-09'. This is our annual refresh" | edit_plan | Finds all TEXT/MTEXT entities containing "2024-01-15". Generates edit_text operations for each instance, replacing with "2026-03-09". Preview shows all changes. Handles MTEXT formatting preservation. |
| 4 | "Run a health check on this file before I archive it in our facility management system" | health | Evaluates drawing quality for archival: text legibility, entity integrity, layer organization, MTEXT formatting consistency. Reports issues that could cause problems in FM software imports. |

---

### Profile 21 — Shop Fabricator

**Who:** Eddie Kowalczyk, shop foreman at PrecisionSteel Fabrication. 25 years of steel fabrication experience. Reads detail drawings daily and programs CNC machines. Needs exact dimensions and mirrored versions of brackets and connection details.
**Document:** `tests/fixtures/dxf_zoo/sourced/gds-polylines.dxf` (DXF)
**Business context:** CNC programming for a run of 200 custom steel brackets. Eddie needs to verify dimensions from the detail drawing, scale the detail to full-size (1:1) for CNC extraction, create a mirror image for the left-hand version, and generate a parts takeoff for the material order.

#### Capabilities exercised
- **scale** — scaling details to full size
- **mirror** — creating left-hand versions
- **Q&A** — dimension and material queries
- **takeoff** — parts list generation

#### Representative prompts
1. "What are the dimensions of the largest polyline shape in this drawing?"
2. "Scale everything to 1:1 — right now it looks like it's at half scale"
3. "Mirror the whole thing across the Y axis for the left-hand version"
4. "Give me a parts takeoff — I need to order material"
5. "How many pieces total am I cutting?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "What are the overall dimensions? I need to verify this matches the cut list before I program the CNC" | qna | Analyzes polyline geometry to determine overall extents (bounding box). Reports width, height, and key dimensions derived from polyline vertex coordinates. |
| 2 | "Scale this to full size — it's drawn at half scale. Scale factor 2.0 from the origin" | edit_plan | Generates scale operation with factor 2.0 about (0,0). Applies to all entities. Preview shows the before/after size. Warns if the result exceeds expected sheet extents. |
| 3 | "Now I need the left-hand version. Mirror everything across the vertical centerline" | edit_plan | Generates mirror operation across the Y-axis (vertical centerline of the drawing extents). Creates mirrored copies of all entities. Preview shows the mirrored result. |
| 4 | "Takeoff — how many pieces, what lengths, what material do I need to order?" | takeoff | Extracts all polyline entities. Calculates total perimeter lengths, individual segment lengths, and entity counts. Groups by layer if different materials are on different layers. Structured for a material order. |

---

### Profile 22 — Solar Installer

**Who:** Chris Nakamura, project designer at SunGrid Solar. 4 years of experience designing residential and commercial solar panel layouts. Currently designing a 150 kW commercial rooftop array on a flat-roof warehouse.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-2Drectangles.dxf` (DXF)
**Business context:** Solar permit application due to the utility and city next week. Chris needs to lay out panel blocks on the roof area, copy arrays to fill the available space, verify panel count for the interconnection application, and generate a takeoff for the material order.

#### Capabilities exercised
- **add_block** — placing solar panel representations
- **copy** — duplicating panel arrays
- **batch** — positioning multiple panels
- **takeoff** — panel count and coverage area

#### Representative prompts
1. "How many rectangles are in this drawing? Those represent roof sections"
2. "Add a solar panel block at 10,10"
3. "Copy that panel to create a 3x5 array with 6-foot spacing"
4. "How many panels total now?"
5. "Takeoff — total panel count and estimated coverage area"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "How many rectangles are in this drawing and what are their sizes? I need to figure out how many panels fit on each roof section" | qna | Counts rectangle entities (closed LWPOLYLINE with 4 vertices). Reports dimensions and areas for each. Helps determine available roof area for panel placement. |
| 2 | "Add a solar panel block at 10,10 on the SOLAR-PANELS layer" | edit_plan | Generates add_block operation. Block "SOLAR-PANEL" at (10,10), layer "SOLAR-PANELS". Preview shows placement relative to the roof rectangle boundaries. |
| 3 | "Copy that panel to make a row of 5, spaced 6 feet apart going east" | edit_plan | Generates four copy operations from the source at (10,10) to (16,10), (22,10), (28,10), and (34,10). Same layer. Preview shows the complete row. |
| 4 | "Give me a takeoff — total panel count and how much roof area they cover. I need this for the interconnection application" | takeoff | Counts all panel blocks/entities. Calculates total coverage area based on panel dimensions. Reports: total panels, total kW (if panel wattage is known), total area covered, and coverage ratio against available roof area. |

---

### Profile 23 — BIM Coordinator

**Who:** Alex Petrov, BIM coordinator at Atlas Architecture + Engineering (350-person A/E firm). 8 years of experience managing BIM standards and model coordination. Currently reviewing 2D DXF exports from Revit for a convention center project.
**Document:** `tests/fixtures/dxf_zoo/r2018_polylines.dxf` (DXF)
**Business context:** Model coordination meeting tomorrow. Alex needs to verify the quality of the 2D DXF exports from Revit (their architects use Revit, but the structural engineer works in AutoCAD). Layer standards need to match the project BIM Execution Plan, and any export artifacts need to be flagged.

#### Capabilities exercised
- **health** — export quality verification
- **compare** — checking against standards (format issues)
- **Q&A** — layer and entity queries
- **summary** — coordination meeting brief

#### Representative prompts
1. "Run a health check on this Revit export"
2. "List all layers and check if they follow AIA layer naming convention"
3. "How many entity types are in this file?"
4. "Summarize this for the coordination meeting"
5. "Are there any Revit export artifacts like proxy entities?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "Health check this file. It's a Revit-to-DXF export and I need to know if the export is clean" | health | Deep health analysis focusing on export quality: checks for proxy entities, exploded blocks, layer name formatting, entity type distribution, coordinate system issues. Reports DXF version (R2018) and any export artifacts. |
| 2 | "List all the layers. Do they follow AIA CAD Layer Guidelines or did Revit mangle the names?" | qna | Extracts all layer names. Compares against AIA layer naming convention (discipline prefix, major group, minor group). Reports which layers conform and which deviate, with suggestions for standard names. |
| 3 | "Summarize this for the coordination meeting — I need to tell the team what's on the structural engineer's sheet" | summary | Returns a coordination-focused summary: describes what's shown, lists disciplines represented, entity counts by type and layer. Framed for a multi-discipline coordination audience. |
| 4 | "Any polylines that look like they might be exploded Revit hatches? Those always cause problems" | qna | Analyzes polyline entities for patterns consistent with exploded hatches: very high vertex counts, repeated patterns, or unusual layer assignments. Reports any suspicious entities with locations. |

---

### Profile 24 — Junior Drafter / Intern

**Who:** Sam Rivera, architecture intern in their first month at a small 10-person firm. Just graduated with a B.Arch and is learning the firm's CAD standards. Being mentored by a senior project architect. More comfortable asking questions than making changes.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-layers.dxf` (DXF)
**Business context:** Training exercise. Sam's mentor gave them a drawing and asked them to explore it — understand the layer structure, try some basic edits, and report back on what they learned. The goal is building CAD literacy, not producing deliverables.

#### Capabilities exercised
- **Q&A** — learning-oriented questions about CAD concepts
- **move** — basic entity manipulation
- **edit_text** — simple text changes
- **summary** — understanding drawing contents

#### Representative prompts
1. "What are layers in a DXF file?"
2. "What layers are in this drawing?"
3. "Can you move the entity closest to 20,20 to 30,30?"
4. "What text is on this drawing?"
5. "Give me a summary of this whole drawing"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "I'm new to this. Can you explain what layers are in this drawing and what they're used for?" | qna | Returns an educational explanation: layers are organizational containers for drawing entities (like transparent overlays). Lists all layers in the drawing with their properties (color, linetype, entity count). Explains naming conventions. |
| 2 | "Move whatever is closest to 20,20 to position 30,30. I want to see how editing works" | edit_plan | Finds the entity nearest to (20,20) using spatial query. Generates move operation to (30,30). Preview clearly shows before/after positions. Good entry point for understanding edits. |
| 3 | "Is there any text on this drawing? If so, change the first one to say 'EDITED BY SAM'" | edit_plan | Searches for TEXT/MTEXT entities. If found, generates edit_text operation on the first text entity, changing content to "EDITED BY SAM". Preview shows the change. If no text exists, reports that clearly. |
| 4 | "Give me a full summary of everything in this drawing. I need to report back to my mentor on what I found" | summary | Returns a comprehensive summary: DXF version, all layers with entity counts, entity types present, spatial extents, block definitions. Presented in an educational format that helps Sam understand drawing organization. |

---

### Profile 25 — Landscape Field Crew Lead (HeyFlora.ai workflow)

**Who:** Marcus Thompson, landscape crew lead at Green Valley Landscapes. 8 years of hands-on landscape installation experience. Reviews plans on a ruggedized tablet at the job site. Prefers short, direct answers — voice-first interaction style.
**Document:** `tests/fixtures/dxf_zoo/sourced/jscad-2Darcs.dxf` (DXF)
**Business context:** On-site for a hardscape installation at a commercial property. Marcus pulled up the plan on his tablet and needs to quickly identify what features are in different areas of the site, confirm what types of elements are along specific boundaries, get a quick field crew brief, and flag any drawing issues the office should fix before tomorrow's concrete pour.

#### Capabilities exercised
- **Q&A** — location-based and type-based queries
- **summary** — quick field crew brief
- **health** — flagging issues for the office
- **takeoff** — material quantities for field verification

#### Representative prompts
1. "What's in the northeast corner of this plan?"
2. "What types of arcs are along the south edge?"
3. "Give me a quick field brief — what are we building today?"
4. "Anything wrong with this drawing I should tell the office about?"
5. "How much curved border are we installing total?"

#### Conversation script (4 turns)

| Turn | Prompt | Expected family | Expected behavior |
|------|--------|----------------|-------------------|
| 1 | "What's in the northeast corner? I'm standing here and I need to know what we're installing" | qna | Spatial query: filters entities by position (upper-right quadrant of the drawing extents). Reports what arc/line entities are in that region, with approximate dimensions. Short, direct answer. |
| 2 | "What types of curves are along the south boundary? The client wants to know if it's all one radius or mixed" | qna | Analyzes arc entities near the bottom edge of the drawing. Reports radii, center points, and whether they're consistent or varied. Direct answer suitable for field communication with the client. |
| 3 | "Give me a quick brief I can read to my crew. What are we looking at and what's the scope?" | summary | Returns a concise field-oriented summary: what's on the drawing, approximate extents, key features, materials implied by the geometry. Written for a 2-minute crew huddle, not a boardroom presentation. |
| 4 | "Anything wrong with this drawing? I don't want to pour concrete and then find out the plan was messed up" | health | Quick health check focused on field-relevant issues: inconsistent dimensions, missing information, conflicting geometry, potential constructability problems. Reports issues the office needs to resolve before the crew proceeds. |

#### Landscape field operations context

This profile models a HeyFlora.ai field-crew workflow for landscape management — the person who reads plans on a tablet at the job site. Voice-first interaction style: short, direct questions about what's where and what to build. Field crews need:
- Spatial Q&A ("what's in the northeast corner?") routed through drawing analysis
- Quick field briefs summarizing scope for crew huddles
- Health checks that flag drawing issues before concrete pours or installations
- Takeoff data (arc lengths, area calculations) for daily progress tracking

**Compliance frameworks checked:**
- **OSHA 29 CFR 1926** — Construction safety standards (relevant for field crew operations)
- **ANSI A300** — Tree care standards (if existing trees border the hardscape installation)
- **ADA/ABA Accessibility Guidelines** — Walkway slopes and clearances for curved hardscape paths

---

## Test Implementation Notes

### Fixture Validation

Before implementing these profiles as automated tests, verify all fixture files exist and load correctly:

```python
PROFILE_FIXTURES = {
    1:  "tests/fixtures/revision/nasty/real_columns/master.dxf",
    2:  "tests/fixtures/dxf_zoo/r2000_blocks.dxf",
    3:  "tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf",
    4:  "tests/fixtures/dxf_zoo/sourced/gds-api-cw750-details.dxf",
    5:  "tests/fixtures/dxf_zoo/sourced/jscad-CustomBlocks.dxf",
    6:  "tests/fixtures/dxf_zoo/sourced/jscad-blocks1.dxf",
    7:  "tests/fixtures/dxf_zoo/sourced/jscad-blocks2.dxf",
    8:  "tests/fixtures/dxf_zoo/sourced/jscad-2Dlines.dxf",
    9:  "tests/fixtures/dxf_zoo/sourced/jscad-2Dcircles.dxf",
    10: "tests/fixtures/test_pdfs/structural_plan.pdf",
    11: "tests/fixtures/test_pdfs/foundation_detail.pdf",
    12: "000-docs/aMULBERRYdsn01.1-STAMPED-SEALED.pdf",
    13: "tests/fixtures/dxf_zoo/sourced/jscad-texts.dxf",
    14: "tests/fixtures/dxf_zoo/sourced/jscad-2Dpolylines.dxf",
    15: "tests/fixtures/dxf_zoo/sourced/jscad-floorplan.dxf",
    16: "tests/fixtures/revision/clean_realworld/master.dxf",
    17: "tests/fixtures/test_pdfs/simple_geometry.pdf",
    18: "000-docs/032-TQ-TEST-sawcuts-sample-drawing.pdf",
    19: "tests/fixtures/dxf_zoo/r12_basic.dxf",
    20: "tests/fixtures/dxf_zoo/sourced/gds-mtext-test.dxf",
    21: "tests/fixtures/dxf_zoo/sourced/gds-polylines.dxf",
    22: "tests/fixtures/dxf_zoo/sourced/jscad-2Drectangles.dxf",
    23: "tests/fixtures/dxf_zoo/r2018_polylines.dxf",
    24: "tests/fixtures/dxf_zoo/sourced/jscad-layers.dxf",
    25: "tests/fixtures/dxf_zoo/sourced/jscad-2Darcs.dxf",
}
```

### Profile-to-Test Mapping

Each profile maps to:
1. **An E2E Playwright test** that uploads the fixture, runs each conversation turn, and verifies the expected response family.
2. **A canary subset** (turns marked as critical) for daily production monitoring.
3. **A regression baseline** capturing response structure for snapshot comparison.

### Coverage Gaps Identified

| Gap | Current coverage | This profiles doc adds |
|-----|-----------------|----------------------|
| PDF uploads | 0 profiles | 5 profiles (10, 11, 12, 17, 18) |
| Revision comparison | 0 multi-doc profiles | 1 profile (16) with file pair |
| Non-technical users | 0 profiles | 2 profiles (17, 24) |
| Field/mobile use | 0 profiles | 2 profiles (10, 25) |
| Landscape management vertical | 0 profiles | 2 profiles (15, 25) |
| Diverse DXF formats | 1 (R2000 only) | 3 formats (R12, R2000, R2018) |
