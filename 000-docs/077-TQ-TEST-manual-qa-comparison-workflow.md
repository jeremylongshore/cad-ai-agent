# Manual QA Test Plan: Drawing Comparison Workflow

**Document**: 077-TQ-TEST
**Author**: Jeremy Longshore
**Date**: 2026-03-28
**Tester**: Opeyemi Ariyo (opeyemiariyo@intentsolutions.io)
**UX Benchmark**: DWG FastView (smooth zoom/pan, fast loading, simple controls, detail inspection)

---

## 1. Purpose & Audience

This test plan is for manual QA of the IntentCAD drawing comparison feature. It's written for someone who has never used CAD software before. You'll be testing whether the app lets users compare two versions of a drawing, see what changed, and decide which changes to keep.

**What we're testing:**
- Can you upload and view DXF drawings?
- Can you compare two drawings and see differences?
- Can you approve/reject individual changes?
- Can you download the result?
- Is the experience smooth and intuitive (benchmark: DWG FastView)?

---

## 2. Setup

### What You Need
- **Browser**: Chrome (latest) -- recommended. Firefox works too.
- **Google Account**: Sign in with `opeyemiariyo@intentsolutions.io`
- **App URL**: https://cad-dxf-agent.web.app
- **Test Files**: Jeremy will provide DXF files. Save them somewhere easy to find on your computer.

### Before You Start
1. Open Chrome
2. Make sure you're signed into Google with your @intentsolutions.io account
3. Have the test DXF files ready on your Desktop or Downloads folder
4. Open a new tab and go to https://cad-dxf-agent.web.app

---

## 3. Glossary

Plain-English definitions for terms you'll see in the app:

| Term | What It Means |
|------|---------------|
| **DXF** | A file format for technical drawings (like blueprints). Think of it like a PDF but for engineering drawings. |
| **Entity** | Any individual thing in a drawing -- a line, a circle, a piece of text, a symbol. |
| **Layer** | Drawings are organized in layers (like transparent sheets stacked on top of each other). Each layer holds related entities. |
| **Master** | The original/baseline drawing -- the "before" version. |
| **Revision** | The updated drawing -- the "after" version. |
| **Alignment** | The app figures out how to line up the two drawings so it can compare them accurately. |
| **Confidence** | How sure the app is that it aligned the drawings correctly (shown as a percentage). |
| **Diff** | The list of differences between the two drawings. |
| **Operation** | A single detected change (e.g., "Line moved 5 units right" or "Text deleted"). |
| **Approve/Reject** | You decide which changes to keep (approve) or discard (reject). |
| **Bundle** | A ZIP file containing the final drawing with your approved changes, plus supporting files. |
| **Profile** | An optional filter that focuses the comparison on specific types of entities (e.g., structural elements only). |

---

## 4. Test Cases -- Login & Upload (TC-001 to TC-005)

### TC-001: Sign In
1. Go to https://cad-dxf-agent.web.app
2. Click "Sign in with Google"
3. Choose your `opeyemiariyo@intentsolutions.io` account
4. **Expected**: You land on the main workspace. You should see an upload area and an empty document library sidebar.
5. **UX Check**: Did the login feel quick? Any delays or error flashes?

### TC-002: Empty State
1. After signing in, look at the main area
2. **Expected**: You should see:
   - A large upload zone (drag & drop area) in the center
   - An empty document library panel on the side
   - A "Compare" tab in the preview panel
   - Clear instructions telling you to upload a file
3. **UX Check**: Is it obvious what you should do next? Are there helpful hints?

### TC-003: Upload a DXF File
1. Take one of the test DXF files Jeremy provided
2. **Method A**: Drag the file from your file explorer and drop it onto the upload zone
3. **Method B**: Click the upload zone, browse to the file, and select it
4. **Expected**:
   - A loading indicator appears while the file processes
   - The drawing appears in the viewer
   - File info shows in the sidebar (entity count, layer count, layer list)
5. **UX Check**:
   - How long did loading take? DWG FastView loads typical files in under 2 seconds.
   - Was there a progress indicator, or did the screen just sit there?
   - Did the drawing appear all at once or did it build up?

### TC-004: Verify File Info
1. After upload, look at the info panel/sidebar
2. **Expected**: You should see:
   - Filename
   - Number of entities
   - Number of layers
   - List of layer names
3. **UX Check**: Is the information clear and readable?

### TC-005: Viewer Interactions
1. **Zoom in**: Use your scroll wheel (scroll up to zoom in)
2. **Zoom out**: Scroll down
3. **Pan**: Click and drag to move around the drawing
4. **Fit to view**: Click the "fit to view" button (square icon in the toolbar)
5. **Zoom buttons**: Try the + and - buttons in the toolbar
6. **Expected**: All interactions should be smooth and responsive
7. **UX Checks** (compare to DWG FastView):
   - Does zooming feel smooth, or does it jump/jitter?
   - Can you pan smoothly across the entire drawing without lag?
   - When zoomed in tight, are small details crisp or blurry?
   - Does "fit to view" snap back to show the whole drawing?
   - Is there any delay between your mouse action and the viewer responding?

---

## 5. Test Cases -- Path 1: Quick Compare (TC-010 to TC-023)

This is the main workflow. You upload a second file to compare against the first.

### TC-010: Open Compare Tab
1. Make sure you have a drawing loaded (from TC-003)
2. Click the "Compare" tab in the preview panel
3. **Expected**: You see options to upload a revision file or compare from library

### TC-011: Upload Revision File
1. Click "Upload Revision (.dxf / .dwg)" button
2. Select the second test DXF file (the "revision")
3. **Expected**: The file uploads and the comparison process begins automatically
4. **UX Check**: Is there a clear progress indicator during comparison?

### TC-012: Verify Alignment
1. After the revision uploads, look for the alignment bar
2. **Expected**: You should see:
   - Alignment method (e.g., "Bounding-box" or "Control-point")
   - Confidence percentage (e.g., "95% confidence")
   - A "Refine" button for manual adjustment
3. **UX Check**: Is the confidence percentage easy to understand? Does high % = good?

### TC-013: Verify Diff Badges
1. Look for the change summary badges
2. **Expected**: You should see colored badges showing:
   - "+N added" (new entities in the revision)
   - "-N removed" (entities deleted in the revision)
   - "~N modified" (entities changed in the revision)
   - "->N moved" (entities repositioned in the revision)
3. The total should match the changes listed below
4. **UX Check**: Are the badges clear? Can you tell at a glance how many changes there are?

### TC-014: Test Split View
1. Look for the view toggle sub-tabs: "Split", "Original", "Revised"
2. Click "Split" -- you should see both drawings side by side
3. Click "Original" -- you should see only the master drawing
4. Click "Revised" -- you should see only the revision drawing
5. **Expected**: Each view loads quickly and shows the correct drawing
6. **UX Check**: Is switching views instant, or is there a delay?

### TC-015: Scroll Through Operations
1. Look at the operation list (the list of detected changes)
2. Scroll through it
3. **Expected**: Each operation shows:
   - Type of change (added, removed, modified, moved)
   - Description of what changed
   - Status (pending -- yellow/neutral)
4. **UX Check**: Is the list easy to read? Can you understand each change?

### TC-016: Click-to-Focus
1. Click on any operation in the list
2. **Expected**: The viewer zooms/pans to show the location of that change
3. Try clicking different operations
4. **UX Check**:
   - Does the viewer smoothly pan to the right location?
   - Can you see the actual change in the drawing?
   - Does it highlight the affected area?

### TC-017: Approve Individual Operations
1. Find an operation in the list
2. Click the approve button (checkmark / green button) next to it
3. **Expected**:
   - The operation status changes to "Approved" (green)
   - The status counters update (e.g., "1 Approved / 4 Pending / 0 Rejected")
4. Try approving a few more operations

### TC-018: Reject Individual Operations
1. Find a pending operation
2. Click the reject button (X / red button) next to it
3. **Expected**:
   - The operation status changes to "Rejected" (red)
   - The status counters update accordingly

### TC-019: Bulk Approve All
1. Click "Approve All" button
2. **Expected**: All remaining pending operations switch to Approved
3. **UX Check**: Does this happen instantly?

### TC-020: Bulk Reject All
1. Click "Reject All" button (you may need to reset first)
2. **Expected**: All operations switch to Rejected
3. **UX Check**: Is there a confirmation dialog, or does it happen immediately?

### TC-021: Apply Approved Changes
1. Make sure you have some approved operations (use Approve All if needed)
2. Click "Apply N Approved Change(s)" button
3. **Expected**:
   - A processing indicator appears
   - Success message displays
   - "Download Bundle (.zip)" button appears
4. **UX Check**: How long does applying take? Is there feedback during the process?

### TC-022: Download Bundle
1. Click "Download Bundle (.zip)"
2. Open the downloaded ZIP file
3. **Expected**: The ZIP should contain files (updated DXF, changelog, etc.)
4. **UX Check**: Does the download start immediately? Is the ZIP a reasonable size?

### TC-023: Edge Case -- Same File
1. Start a new comparison
2. Upload the SAME DXF file as both master and revision
3. **Expected**: The app should detect 0 changes (no diff badges, empty operation list)
4. **UX Check**: Does the app clearly communicate "no changes found"?

---

## 6. Test Cases -- Path 2: Compare from Library (TC-030 to TC-036)

### TC-030: Save Files to Library
1. Upload the first DXF file and save it to the Document Library
2. Upload the second DXF file and save it too
3. **Expected**: Both files appear in the Document Library sidebar

### TC-031: Open Compare from Library
1. In the Document Library, look for the "Compare from library" button
2. Click it
3. **Expected**: A modal/dialog opens with document selection

### TC-032: Select Master and Revision
1. In the comparison modal:
   - Select one document as "Master" (baseline)
   - Select the other as "Revision" (updated)
2. **Expected**: Both dropdowns/selectors show your saved documents

### TC-033: Optional Profile Selection
1. Look for a "Profile" selector in the comparison modal
2. If available, try selecting a profile (e.g., "structural")
3. **Expected**: The profile is selected. This will filter what types of changes are shown.

### TC-034: Start Library Comparison
1. Click "Compare" button in the modal
2. **Expected**: The same comparison review flow starts (alignment, diff badges, operation list)
3. You should see the same workflow as TC-012 through TC-022

### TC-035: Edge Case -- Same Document
1. Open Compare from Library
2. Try to select the same document for both Master and Revision
3. **Expected**: The app should prevent this (greyed out option, error message, or disabled Compare button)

### TC-036: Cancel Comparison
1. Open Compare from Library
2. Press Escape or click a Cancel/Close button
3. **Expected**: Modal closes, nothing changes in the workspace

---

## 7. Test Cases -- Advanced Features (TC-040 to TC-044)

### TC-040: Keyboard Navigation
1. During a comparison review (operations list visible):
2. Press **Arrow Down** to move to the next operation
3. Press **Arrow Up** to move to the previous operation
4. Press **Enter** or **Space** to toggle approve/reject on the focused operation
5. **Expected**: Keyboard navigation works smoothly through the list
6. **UX Check**: Can you do the entire review without touching the mouse?

### TC-041: All Rejected -- Apply Disabled
1. Use "Reject All" to reject every operation
2. Look at the "Apply" button
3. **Expected**: The button should be disabled with a message like "Review all changes before applying" or "No approved changes"

### TC-042: Control Point Refinement
1. After initial alignment, click the "Refine" button
2. **Expected**: You enter a point-picking mode (crosshair cursor)
3. Pick 4 matching points (click a recognizable point on the original, then the same point on the revision)
4. Click "Re-align"
5. **Expected**: The alignment recalculates, potentially with higher confidence
6. **UX Check**: Is the point-picking process clear? Do you know what to click?

### TC-043: Replace Revision Mid-Workflow
1. While in comparison review, upload a different revision file
2. **Expected**: The previous comparison is discarded and a new comparison starts
3. **UX Check**: Is there a warning about losing current review progress?

### TC-044: Large/Complex Drawing Performance
1. If Jeremy provides a large test file, use it for this test
2. Upload it and compare with its revision
3. **Expected**: The app handles it without crashing
4. **UX Checks** (DWG FastView benchmark):
   - Does the drawing load without the browser freezing?
   - Can you zoom and pan smoothly on the large drawing?
   - Does the comparison complete in a reasonable time?
   - Is the operation list responsive when scrolling?

---

## 8. Test Cases -- Secondary Features (TC-050 to TC-058)

### TC-050: Document Library -- Save
1. Upload a DXF file
2. Look for a "Save to Library" button
3. Click it
4. **Expected**: File appears in the Document Library sidebar

### TC-051: Document Library -- Load
1. Click on a saved document in the Library
2. **Expected**: The drawing loads into the viewer

### TC-052: Document Library -- Delete
1. Click the delete button on a saved document
2. **Expected**: A confirmation dialog appears ("Are you sure?")
3. Confirm deletion
4. **Expected**: Document is removed from the library

### TC-053: Chat Feature
1. With a drawing loaded, look for a chat/prompt input area
2. Type: "what layers are in this drawing?"
3. Press Enter or click Send
4. **Expected**: The app responds with a list of layers from the loaded drawing
5. **UX Check**: Is the response fast? Is it accurate?

### TC-054: New File Button
1. Click "New File" or "Reset" button
2. **Expected**: The workspace resets -- viewer clears, you're back to the upload state
3. **UX Check**: Is there a confirmation if you have unsaved work?

### TC-055: Sign Out
1. Find the sign out / profile button
2. Click "Sign Out"
3. **Expected**: You're redirected to the login screen
4. **UX Check**: Is sign out easy to find?

### TC-056: Wrong File Type
1. Try uploading a non-DXF file (a .jpg, .txt, or .docx)
2. **Expected**: A clear error message appears (e.g., "Unsupported file type")
3. **UX Check**: Is the error message helpful? Does it tell you what file types are accepted?

### TC-057: Storage Indicator
1. After saving some documents, look for a storage usage indicator
2. **Expected**: Shows how much storage you're using

### TC-058: Multiple Browser Tabs
1. Open the app in two tabs simultaneously
2. Upload a file in one tab
3. **Expected**: The other tab should still work independently without issues

---

## 9. UX Observation Checklist

Watch for these across ALL tests. Note anything that feels off.

| Category | What to Watch For | Notes |
|----------|-------------------|-------|
| **Loading** | Is there a spinner/progress bar? Or does the screen freeze? | |
| **Button Labels** | Can you tell what each button does without guessing? | |
| **Feedback** | After every action, do you know what happened? | |
| **Error Messages** | Are they helpful or cryptic? | |
| **Disabled States** | Are greyed-out buttons explained (tooltip/message)? | |
| **Empty States** | When there's no data, is there helpful guidance? | |
| **Zoom/Pan** | Smooth and responsive like DWG FastView? | |
| **Large Drawings** | Any lag when loading, scrolling, or zooming? | |
| **Detail Inspection** | Zoomed in tight -- crisp details or blurry? | |
| **Navigation** | Can you find your way around without help? | |
| **Responsive** | Does it work if you resize the browser window? | |
| **Color/Contrast** | Can you read everything clearly? | |
| **Consistency** | Do similar actions work the same way everywhere? | |

---

## 10. Bug Report Template

When you find a bug, copy this template and fill it in:

```
**Bug ID**: BUG-XXX
**Test Case**: TC-XXX
**Summary**: (One-line description)

**Steps to Reproduce**:
1.
2.
3.

**Expected**: What should have happened
**Actual**: What actually happened

**Screenshot**: (Paste or attach)
**Browser**: Chrome XX / Firefox XX
**OS**: Windows / Mac / Linux
**Severity**: Critical / Major / Minor / Cosmetic
**Date**: YYYY-MM-DD
```

### Severity Guide
- **Critical**: App crashes, data loss, can't complete the main workflow
- **Major**: Feature doesn't work as expected, but there's a workaround
- **Minor**: Cosmetic issue that doesn't block functionality
- **Cosmetic**: Typo, alignment issue, minor visual glitch

---

## 11. Test Execution Log

Track your progress here. Update the Status column as you go.

| TC-ID | Description | Status | Notes | Date |
|-------|-------------|--------|-------|------|
| TC-001 | Sign In | | | |
| TC-002 | Empty State | | | |
| TC-003 | Upload DXF | | | |
| TC-004 | File Info | | | |
| TC-005 | Viewer Interactions | | | |
| TC-010 | Open Compare Tab | | | |
| TC-011 | Upload Revision | | | |
| TC-012 | Verify Alignment | | | |
| TC-013 | Verify Diff Badges | | | |
| TC-014 | Split View | | | |
| TC-015 | Scroll Operations | | | |
| TC-016 | Click-to-Focus | | | |
| TC-017 | Approve Operations | | | |
| TC-018 | Reject Operations | | | |
| TC-019 | Bulk Approve All | | | |
| TC-020 | Bulk Reject All | | | |
| TC-021 | Apply Changes | | | |
| TC-022 | Download Bundle | | | |
| TC-023 | Same File Edge Case | | | |
| TC-030 | Save to Library | | | |
| TC-031 | Compare from Library | | | |
| TC-032 | Select Master/Revision | | | |
| TC-033 | Profile Selection | | | |
| TC-034 | Start Library Compare | | | |
| TC-035 | Same Document Edge Case | | | |
| TC-036 | Cancel Comparison | | | |
| TC-040 | Keyboard Navigation | | | |
| TC-041 | All Rejected State | | | |
| TC-042 | Control Point Refinement | | | |
| TC-043 | Replace Revision | | | |
| TC-044 | Large Drawing Perf | | | |
| TC-050 | Library Save | | | |
| TC-051 | Library Load | | | |
| TC-052 | Library Delete | | | |
| TC-053 | Chat Feature | | | |
| TC-054 | New File | | | |
| TC-055 | Sign Out | | | |
| TC-056 | Wrong File Type | | | |
| TC-057 | Storage Indicator | | | |
| TC-058 | Multiple Tabs | | | |

---

**Questions?** Message Jeremy on Slack or create a GitHub issue at https://github.com/jeremylongshore/cad-dxf-agent/issues
