# CAD DXF Agent: Web App Quick Reference
*Generated: 2026-03-02 | v0.4.0*

## What It Does

CAD DXF Agent is a web application that lets you edit CAD drawings using plain English. Upload your drawing, describe the change you want, review the AI's plan, and download the result. Your original file is never modified.

## Getting Started

### Sign In

No account required. When you visit the app, you're automatically signed in as a guest and can start working immediately.

**Optional**: Create an account (email/password or Google sign-in) to save your preferences across sessions.

### Supported File Types

| Format | Extension | Notes |
|--------|-----------|-------|
| AutoCAD DXF | `.dxf` | Native format, best results |
| AutoCAD DWG | `.dwg` | Auto-converted to DXF on upload |
| PDF drawings | `.pdf` | Auto-converted, geometry extracted |

Maximum file size: **50 MB**

## Workflow 1: AI-Assisted Editing

This is the main workflow — edit your drawing by describing changes in plain language.

### Step 1: Upload Your Drawing

Drag and drop your file onto the upload zone, or click to browse. The app analyzes your file and shows:
- A visual preview of the drawing (center panel)
- File stats: entity count, layer count, layer names (left sidebar)

### Step 2: Describe Your Edit

Use the chat panel (right side) to tell the AI what to change. Type in plain English:

| What You Want | Example Prompt |
|---------------|----------------|
| Move something | "Move column A1 24 feet east" |
| Change text | "Rename label FOOTING F1 to FOOTING F2" |
| Delete something | "Delete the north elevation note" |
| Add a block | "Add a column mark at grid B3" |

Press **Enter** to send. **Shift+Enter** for a new line.

**Tip**: If you're not sure what to say, click one of the suggestion chips that appear in an empty chat.

### Step 3: Review the Plan

The AI returns a list of planned operations. Each shows:
- **Type badge**: move / edit / delete / add (color-coded)
- **Description**: What will change

You can **check/uncheck** individual operations to include or exclude them.

### Step 4: Apply Changes

Click **"Apply Changes"** to execute the selected operations. The preview automatically switches to the **Edited** tab showing the modified drawing.

### Step 5: Download

Click **"Download Edited DXF"** to save your edited file. The original is never modified — you always get a new file.

### Follow-Up Edits

After applying changes, you can continue chatting to make additional edits. The AI works on the latest version of the drawing. Quick-action chips appear after each response:
- "Download edited DXF"
- "Make another edit"

## Workflow 2: Revision Comparison

Compare two versions of a drawing to see what changed — useful for tracking revisions from collaborators or across project phases.

### Step 1: Upload the Master Drawing

Upload your baseline/original drawing using the main upload zone (same as the editing workflow).

### Step 2: Switch to Compare Tab

Click the **"Compare"** tab in the preview panel.

### Step 3: Upload the Revision

Click **"Upload Revision"** and select the newer version of the drawing (.dxf or .dwg).

**Optional**: Select a **Comparison Profile** before uploading (e.g., "structural" to focus only on lines, polylines, circles, arcs, and blocks — ignoring title blocks and notes).

### Step 4: Review Alignment

The system auto-aligns the two drawings. You'll see:
- **Method**: How alignment was performed (Identity, Translation, Rigid, etc.)
- **Confidence**: A percentage bar showing alignment quality
- **Offset/Rotation**: If the drawings needed repositioning

If confidence is below 70%, a warning appears suggesting you provide control points.

### Step 5: Review the Diff

A summary shows color-coded change counts:
- **Green (+N)**: Entities added in revision
- **Red (-N)**: Entities removed from original
- **Yellow (~N)**: Entities modified
- **Blue (arrow N)**: Entities moved

### Step 6: Approve or Reject Changes

Each detected change appears as a card with:
- Type badge and description
- Match confidence percentage
- **Approve** / **Reject** buttons

Use **"Approve All"** or **"Reject All"** for bulk actions. You must decide on every change before applying (no pending items allowed).

### Step 7: Apply and Download

Click **"Apply N Approved Changes"** to merge approved changes into the master drawing. Then click **"Download Bundle (.zip)"** to get:
- Updated master DXF
- Diff overlay DXF (visual comparison layer)
- Changelog (text summary of all changes)
- Alignment result data
- Metadata

## Protected Layers

The following layers cannot be edited (the AI will refuse operations on them):

| Layer | Purpose |
|-------|---------|
| TITLE | Title block content |
| TITLEBLOCK | Title block border |
| SEAL | Professional seal/stamp |
| REVISION | Revision history table |

This protects critical drawing metadata from accidental changes.

## What the AI Can Do

| Operation | Description | Example |
|-----------|-------------|---------|
| **Move** | Relocate entities by distance | "Move the wall 12 inches north" |
| **Edit Text** | Change text content | "Change OFFICE to CONFERENCE ROOM" |
| **Delete** | Remove entities | "Remove the staircase on layer STAIRS" |
| **Add Block** | Insert a predefined block | "Add column mark at B3" |

**Supported entity types**: Lines, polylines, text, multiline text, blocks, circles, arcs, ellipses, dimensions, hatches, splines, leaders, and solids.

## Chat Tips

- **Be specific**: Reference layer names, entity types, or locations when possible
- **One change at a time**: Start with simple edits, add complexity as needed
- **Use the suggestions**: Click the pre-built prompt chips for quick actions
- **Retry if needed**: Click "Retry" on any AI response to get a different plan
- **Export chat**: Click "Export" to copy the full conversation to your clipboard
- **Clear and restart**: Click "Clear chat" to start a fresh conversation

## Troubleshooting

| Issue | What to Do |
|-------|------------|
| Upload fails | Check file is .dxf, .dwg, or .pdf and under 50MB |
| AI doesn't respond | Wait up to 60 seconds for complex drawings |
| Wrong entities changed | Be more specific — name layers or positions |
| Can't edit title block | Title/seal/revision layers are protected by design |
| Preview looks wrong | Try uploading a different file format (.dxf preferred) |
| Lost my session | Upload the file again to start a new session |
| Download not working | Ensure you've applied changes first |

## Key Contacts

| Role | Contact |
|------|---------|
| Product Owner | Jeremy Longshore |
| Client / Domain Expert | Tonatiuh Nava Razon |
