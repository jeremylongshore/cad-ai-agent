# GitHub Issues - Ready to Copy & Paste

Each issue below is formatted for GitHub. Just copy and paste into new issues.

---

## Issue #1: Document Library Feature Not Discoverable / Missing

**Labels:** `critical`, `ux`, `blocked-testing`

```markdown
## 🔴 Critical: Document Library Feature Not Discoverable / Missing

**Test Cases:** TC-030, TC-031, TC-050, TC-051, TC-052  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
The Document Library sidebar and all library-related functionality cannot be found in the application. This blocks testing of the entire "Compare from Library" workflow (7 test cases).

### Steps to Reproduce
1. Sign in to https://cad-dxf-agent.web.app
2. Upload and view a DXF file
3. Look for "Save to Library" button or option
4. Look for Document Library sidebar/panel
5. Search entire UI for library-related controls

### Expected Behavior
- Should see a Document Library sidebar/panel
- Should see a "Save to Library" button after uploading files
- Should be able to save files to the library
- Should be able to access saved documents for comparison

### Actual Behavior
- No Document Library panel visible
- No "Save to Library" button found
- Unable to locate any library functionality
- Cannot test TC-030 through TC-036 (library comparison workflow)

### Impact
- Core feature completely inaccessible
- Entire comparison-from-library workflow cannot be used
- Users cannot save or reuse drawings
- **Even if the feature exists, it cannot be found - critical UX discoverability issue**

### Priority
**Critical** - Blocks major workflow and multiple test cases

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md
```

---

## Issue #2: Diff Badges Not Displayed in Comparison View

**Labels:** `major`, `ui`, `comparison`

```markdown
## 🟠 Major: Diff Badges Not Displayed in Comparison View

**Test Cases:** TC-013, TC-015  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
The diff badges showing change summary (+N added, -N removed, ~N modified, ->N moved) are not visible after comparison. Additionally, cannot find the "scroll through operations" functionality.

### Steps to Reproduce
1. Upload a master DXF file
2. Click "Compare" tab
3. Upload a revision DXF file
4. Wait for comparison to complete
5. Look for diff badges showing change counts
6. Look for operation list to scroll through

### Expected Behavior
- Should see colored badges displaying:
  - "+N added" (new entities)
  - "-N removed" (deleted entities)
  - "~N modified" (changed entities)
  - "->N moved" (repositioned entities)
- Should see a scrollable operation list
- Total should match the number of changes

### Actual Behavior
- Diff badges not visible
- Cannot find scroll through operations functionality
- No visual summary of changes detected

### Impact
- Users cannot quickly assess the scope of changes
- Cannot tell at a glance how many changes occurred
- Comparison results not presented effectively

### Priority
**Major** - Core comparison feature missing critical UI elements

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 5 (TC-013)
```

---

## Issue #3: Keyboard Navigation Only Works for First 3 Operations

**Labels:** `major`, `accessibility`, `keyboard-navigation`

```markdown
## 🟠 Major: Keyboard Navigation Only Works for First 3 Operations

**Test Cases:** TC-040  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
Arrow key navigation in the operation list only works for the first 3 items. Users must manually scroll with mouse wheel to access remaining operations. Enter/Space key also does not toggle approve/reject status.

### Steps to Reproduce
1. Complete a comparison with more than 3 operations
2. Use Arrow Down key to navigate through operations
3. Try to navigate beyond the 3rd operation
4. Use Arrow Up key from a lower position
5. Try using Enter or Space to approve/reject an operation

### Expected Behavior
- Arrow Down should move to next operation through entire list
- Arrow Up should move to previous operation through entire list
- Enter or Space should toggle approve/reject on focused operation
- Should be able to complete entire review using only keyboard

### Actual Behavior
- Arrow Down only navigates through first 3 operations
- Arrow Up only navigates through first 3 operations (upward)
- Must use mouse scroll wheel to access operations 4+
- Enter/Space keys do not toggle approve/reject status
- Cannot complete review without mouse

### Impact
- **Accessibility issue** for keyboard-only users
- Inefficient workflow for users who prefer keyboard navigation
- Violates UX benchmark expectation of full keyboard support
- Fails WCAG accessibility guidelines

### Priority
**Major** - Accessibility issue blocking keyboard-only users

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 7 (TC-040)
```

---

## Issue #4: Control Point Refinement Confidence Remains at 0%

**Labels:** `major`, `comparison`, `alignment`

```markdown
## 🟠 Major: Control Point Refinement Confidence Remains at 0%

**Test Cases:** TC-042  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
When using the "Refine" button to improve alignment via control point selection, the confidence percentage stays at 0% after re-alignment, and point-picking mode (crosshair cursor) does not appear.

### Steps to Reproduce
1. Complete an initial comparison
2. Note the initial alignment confidence percentage
3. Click the "Refine" button
4. Observe cursor (should show crosshair for point-picking mode)
5. Attempt to select 4 matching control points
6. Click "Re-align"
7. Observe the confidence percentage after recalculation

### Expected Behavior
- Clicking "Refine" should enter point-picking mode with crosshair cursor
- User should be able to select 4 matching points on master and revision
- After clicking "Re-align", confidence should recalculate
- Confidence percentage should update (potentially higher than initial)

### Actual Behavior
- Crosshair cursor/point-picking mode does not appear
- After re-alignment attempt, confidence remains at 0%
- Refinement process does not improve alignment

### Impact
- Users cannot manually improve poor automatic alignments
- Drawings with low initial confidence cannot be refined
- Critical workflow for complex comparisons is broken

### Priority
**Major** - Critical feature for handling difficult alignments is non-functional

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 7 (TC-042)
```

---

## Issue #5: No Warning When Replacing Revision Mid-Workflow

**Labels:** `minor`, `ux`, `data-loss-risk`

```markdown
## 🟡 Minor: No Warning When Replacing Revision Mid-Workflow

**Test Cases:** TC-043  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
When uploading a different revision file during an active comparison review, the previous comparison is discarded without warning. Users lose all approve/reject decisions without confirmation.

### Steps to Reproduce
1. Complete a comparison between two files
2. Begin reviewing operations (approve/reject some changes)
3. While still in review, upload a different revision file
4. Observe if any warning/confirmation dialog appears

### Expected Behavior
- Should show a warning dialog
- Message should indicate that current review progress will be lost
- Should offer "Cancel" and "Continue" options
- User should be able to cancel and keep current comparison

### Actual Behavior
- No warning or confirmation dialog appears
- Previous comparison immediately discarded
- All approve/reject decisions lost without notice
- New comparison starts immediately

### Impact
- User may accidentally lose significant review work
- No opportunity to save or reconsider before data loss
- Violates UX best practice for destructive actions

### Recommendation
Add confirmation dialog: *"Uploading a new revision will discard your current review progress. Continue?"*

### Priority
**Minor** - Data loss risk, but recoverable by re-reviewing

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 7 (TC-043)
```

---

## Issue #6: No Confirmation When Using "New File" Button

**Labels:** `minor`, `ux`, `data-loss-risk`

```markdown
## 🟡 Minor: No Confirmation When Using "New File" Button

**Test Cases:** TC-054  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
Clicking the "New File" or "Reset" button immediately clears the workspace without confirmation, potentially losing unsaved work.

### Steps to Reproduce
1. Upload a file and complete some work (comparison, review, etc.)
2. Click the "New File" or "Reset" button
3. Observe if any confirmation dialog appears

### Expected Behavior
- Should show confirmation dialog if there is unsaved work
- Message should warn that current work will be lost
- Should offer "Cancel" and "Continue" options

### Actual Behavior
- No confirmation dialog appears
- Workspace immediately resets
- All current work is lost without warning
- Returns to empty upload state

### Impact
- Accidental clicks can lose significant work
- No safety net for user error
- Frustrating UX for users who expect confirmation

### Recommendation
Add confirmation dialog: *"Starting a new file will clear your current work. Continue?"*

### Priority
**Minor** - UX improvement to prevent accidental data loss

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 8 (TC-054)
```

---

## Enhancement Request: Add Message for Disabled Apply Button

**Labels:** `enhancement`, `ux`, `low-priority`

```markdown
## Enhancement: Add Message for Disabled Apply Button

**Test Cases:** TC-041  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
When all operations are rejected, the "Apply" button is correctly disabled, but no helpful message explains why it's disabled.

### Current Behavior
- Button is properly disabled (correct functionality)
- No tooltip or message explains why

### Suggested Enhancement
Add tooltip or inline message: *"No approved changes to apply. Please approve at least one operation."*

### Priority
**Low** - Enhancement, not a bug. Current functionality is correct.

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 7 (TC-041)
```

---

## Investigation Needed: Operation List Scrolling Performance

**Labels:** `needs-investigation`, `performance`

```markdown
## 🔍 Investigation Needed: Operation List Scrolling Performance

**Test Cases:** TC-044  
**Tester:** @opeyemiariyo  
**Browser:** Chrome (latest)

### Description
The operation list is not responsive when scrolling, particularly with larger comparisons.

### Current Information
- Marked as failure during testing
- Specific lag conditions not yet documented

### Needed Information
- Does the lag occur only with large file comparisons?
- Is it a rendering issue or data loading issue?
- What is the approximate number of operations where lag becomes noticeable?
- Browser console errors or warnings?

### Suggested Next Steps
1. Test with various file sizes
2. Document specific lag behavior
3. Check browser performance profiling
4. Determine if virtual scrolling could help

### Priority
**Medium** - Needs investigation to determine severity and root cause

### Reference
Test Plan: 077-TQ-TEST-manual-qa-comparison-workflow.md, Section 7 (TC-044)
```

---

## 📋 Quick Copy Checklist

When creating issues in GitHub, remember to:
- [ ] Copy issue text from above
- [ ] Add appropriate labels (critical, major, minor, enhancement)
- [ ] Assign to appropriate team member
- [ ] Link to test plan document
- [ ] Add to project board/milestone
- [ ] Cross-reference related issues

## 🎯 Recommended Issue Order

Create in this order for maximum impact:

1. **Issue #1** - Document Library (Critical, blocks testing)
2. **Issue #2** - Diff Badges (Major, core UI missing)
3. **Issue #3** - Keyboard Navigation (Major, accessibility)
4. **Issue #4** - Control Point Refinement (Major, feature broken)
5. **Issue #5** - Replace Revision Warning (Minor, data loss risk)
6. **Issue #6** - New File Confirmation (Minor, data loss risk)
7. **Enhancement** - Apply Button Message (Low priority)
8. **Investigation** - Scrolling Performance (Needs more info)
