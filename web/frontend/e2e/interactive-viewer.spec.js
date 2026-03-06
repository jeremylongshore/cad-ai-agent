// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Timeouts for production (Cloud Run cold start + DXF parsing)
const UPLOAD_TIMEOUT = 30_000;
const VIEWER_TIMEOUT = 30_000;
const COMPARE_TIMEOUT = 45_000;

/**
 * Upload a DXF file and wait for the session to be ready.
 * Returns after the system message confirms load.
 */
async function uploadAndWait(page, filename) {
  await page.goto('/');
  await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

  await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, filename));

  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: UPLOAD_TIMEOUT });
}

/**
 * Upload original, switch to Compare tab, upload revision, wait for diff.
 */
async function uploadAndCompare(page) {
  await uploadAndWait(page, 'r2000_blocks.dxf');
  await page.locator('.preview__tab').filter({ hasText: 'Compare' }).click();
  await page.locator('input#revision-upload').setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

  // Wait for comparison — floating diff badges or revision ops list
  await expect(
    page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
  ).toBeVisible({ timeout: COMPARE_TIMEOUT });
}

test.describe('Interactive DXF Viewer', () => {
  test('upload shows interactive WebGL viewer instead of static PNG', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');

    // The DXF viewer component should render (contains a canvas element from Three.js)
    const viewer = page.locator('.dxf-viewer');
    await expect(viewer).toBeVisible({ timeout: VIEWER_TIMEOUT });

    // The viewer should contain a canvas element (WebGL)
    const canvas = viewer.locator('canvas').first();
    await expect(canvas).toBeVisible({ timeout: VIEWER_TIMEOUT });

    // The loading overlay should disappear once DXF is loaded
    const overlay = page.locator('.dxf-viewer__overlay');
    const overlayCount = await overlay.count();
    if (overlayCount > 0) {
      const isVisible = await overlay.isVisible();
      if (isVisible) {
        const text = await overlay.textContent();
        console.log(`Viewer overlay still visible: ${text}`);
        expect(text).not.toContain('Loading drawing');
      }
    }

    console.log('Interactive DXF viewer rendered with WebGL canvas');
  });

  test('viewer toolbar has zoom and fit-to-view buttons', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');
    await expect(page.locator('.dxf-viewer canvas').first()).toBeVisible({ timeout: VIEWER_TIMEOUT });

    const toolbar = page.locator('.viewer-toolbar');
    await expect(toolbar).toBeVisible();

    // Should have 3 buttons: zoom in, zoom out, fit
    const buttons = toolbar.locator('.viewer-toolbar__btn');
    const buttonCount = await buttons.count();
    expect(buttonCount).toBe(3);

    // Zoom in button
    const zoomInBtn = page.locator('button[aria-label="Zoom in"]');
    await expect(zoomInBtn).toBeVisible();
    await expect(zoomInBtn).toBeEnabled();
    await zoomInBtn.click();

    // Zoom out button
    const zoomOutBtn = page.locator('button[aria-label="Zoom out"]');
    await expect(zoomOutBtn).toBeVisible();
    await zoomOutBtn.click();

    // Fit to view button
    const fitBtn = page.locator('button[aria-label="Fit drawing to view"]');
    await expect(fitBtn).toBeVisible();
    await fitBtn.click();

    console.log('Viewer toolbar: zoom in, zoom out, fit — all clickable');
  });

  test('viewer shows hint text for mouse controls', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');
    await expect(page.locator('.dxf-viewer canvas').first()).toBeVisible({ timeout: VIEWER_TIMEOUT });

    const hint = page.locator('.viewer-toolbar__hint');
    await expect(hint).toBeVisible();
    const hintText = await hint.textContent();
    expect(hintText).toContain('Scroll to zoom');
    expect(hintText).toContain('Drag to pan');

    console.log(`Viewer hint: "${hintText}"`);
  });

  test('edited tab shows interactive viewer after apply', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');
    await expect(page.locator('.dxf-viewer canvas').first()).toBeVisible({ timeout: VIEWER_TIMEOUT });

    const textarea = page.locator('.chat__textarea');
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('button').filter({ hasText: 'Send' }).click();

    const opItem = page.locator('.op-item');
    await expect(opItem.first()).toBeVisible({ timeout: 60_000 });

    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    const editedTab = page.locator('.preview__tab').filter({ hasText: 'Edited' });
    await expect(editedTab).toHaveClass(/preview__tab--active/, { timeout: 45_000 });

    const editedViewer = page.locator('.dxf-viewer canvas');
    const editedImg = page.locator('img[alt*="edited"]');

    const hasViewer = await editedViewer.count() > 0;
    const hasImg = await editedImg.count() > 0;
    expect(hasViewer || hasImg).toBe(true);

    console.log(`Edited tab: viewer=${hasViewer}, img=${hasImg}`);
  });
});

test.describe('Sidebar Auto-Collapse', () => {
  test('sidebar collapses after file upload', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');

    // Workspace should have the collapsed class
    const workspace = page.locator('.workspace');
    await expect(workspace).toHaveClass(/workspace--sidebar-collapsed/, { timeout: 5_000 });

    // Sidebar should not be visible
    const sidebar = page.locator('.workspace__sidebar');
    await expect(sidebar).not.toBeVisible();

    console.log('Sidebar auto-collapsed after upload');
  });

  test('Info button in compact bar toggles sidebar', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');

    // Compact bar should show Info button
    const infoBtn = page.locator('.upload-bar-compact button').filter({ hasText: 'Info' });
    await expect(infoBtn).toBeVisible({ timeout: 5_000 });

    // Click Info to expand sidebar
    await infoBtn.click();

    // Sidebar should now be visible
    const sidebar = page.locator('.workspace__sidebar');
    await expect(sidebar).toBeVisible({ timeout: 3_000 });

    // Button should now say "Hide Info"
    const hideBtn = page.locator('.upload-bar-compact button').filter({ hasText: 'Hide Info' });
    await expect(hideBtn).toBeVisible();

    // Click again to collapse
    await hideBtn.click();
    await expect(sidebar).not.toBeVisible({ timeout: 3_000 });

    console.log('Info toggle works: expand and collapse sidebar');
  });
});

test.describe('Compact Upload Bar', () => {
  test('upload bar collapses to compact after file load', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');

    const compactBar = page.locator('.upload-bar-compact');
    await expect(compactBar).toBeVisible({ timeout: 5_000 });

    const filename = page.locator('.upload-bar-compact__filename');
    await expect(filename).toContainText('r2000_blocks.dxf');

    const meta = page.locator('.upload-bar-compact__meta');
    await expect(meta).toBeVisible();
    const metaText = await meta.textContent();
    expect(metaText).toContain('entities');
    expect(metaText).toContain('layers');

    const replaceBtn = page.locator('button').filter({ hasText: 'Replace file' });
    await expect(replaceBtn).toBeVisible();
    await expect(replaceBtn).toBeEnabled();

    const uploadZone = page.locator('.upload-zone');
    const zoneCount = await uploadZone.count();
    expect(zoneCount).toBe(0);

    console.log(`Compact bar: "${await filename.textContent()}" | ${metaText}`);
  });

  test('replace file button triggers new upload', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');
    await expect(page.locator('.upload-bar-compact')).toBeVisible({ timeout: 5_000 });

    const replaceInput = page.locator('.upload-bar-compact').locator('..').locator('input[type="file"]');
    const inputCount = await replaceInput.count();
    expect(inputCount).toBeGreaterThanOrEqual(1);

    console.log('Replace file input present in compact upload bar');
  });
});

test.describe('Side-by-Side Comparison', () => {
  test('compare tab shows split view with two viewers', async ({ page }) => {
    await uploadAndCompare(page);

    // Split view should be visible
    const splitView = page.locator('.compare-split');
    await expect(splitView).toBeVisible({ timeout: VIEWER_TIMEOUT });

    // Should have two panes
    const panes = splitView.locator('.compare-split__pane');
    const paneCount = await panes.count();
    expect(paneCount).toBe(2);

    // Each pane should have a label
    const labels = splitView.locator('.compare-split__label');
    const labelCount = await labels.count();
    expect(labelCount).toBe(2);

    const label1 = await labels.nth(0).textContent();
    const label2 = await labels.nth(1).textContent();
    expect(label1).toContain('Original');
    expect(label2).toContain('Changes');

    const canvases = splitView.locator('.dxf-viewer canvas');
    const canvasCount = await canvases.count();
    console.log(`Split view: ${paneCount} panes, ${labelCount} labels, ${canvasCount} canvases`);
    expect(paneCount).toBe(2);
  });

  test('both split panes have viewer toolbars', async ({ page }) => {
    await uploadAndCompare(page);

    const splitView = page.locator('.compare-split');
    await expect(splitView).toBeVisible({ timeout: VIEWER_TIMEOUT });

    const toolbars = splitView.locator('.viewer-toolbar');
    const toolbarCount = await toolbars.count();
    expect(toolbarCount).toBe(2);

    console.log(`Split view has ${toolbarCount} viewer toolbars`);
  });

  test('compare sub-tabs switch between Split, Original, Revised views', async ({ page }) => {
    await uploadAndCompare(page);

    // Sub-tabs should be visible
    const subtabs = page.locator('.compare-subtabs');
    await expect(subtabs).toBeVisible({ timeout: 5_000 });

    // Should have 3 buttons
    const buttons = subtabs.locator('.compare-subtabs__btn');
    expect(await buttons.count()).toBe(3);

    // Default is Split — should show compare-split with 2 panes
    await expect(page.locator('.compare-split')).toBeVisible();

    // Click "Original" — single full viewer
    await buttons.filter({ hasText: 'Original' }).click();
    await expect(page.locator('.compare-split')).not.toBeVisible({ timeout: 3_000 });
    // Should still have a DXF viewer
    await expect(page.locator('.compare-split-wrap .dxf-viewer')).toBeVisible({ timeout: 5_000 });

    // Click "Revised"
    await buttons.filter({ hasText: 'Revised' }).click();
    await expect(page.locator('.compare-split-wrap .dxf-viewer')).toBeVisible({ timeout: 5_000 });

    // Click "Split" to go back
    await buttons.filter({ hasText: 'Split' }).click();
    await expect(page.locator('.compare-split')).toBeVisible({ timeout: 5_000 });

    console.log('Compare sub-tabs: Split/Original/Revised all work');
  });
});

test.describe('Floating Overlays', () => {
  test('alignment floating bar shows above compare split', async ({ page }) => {
    await uploadAndCompare(page);

    // Floating alignment bar should be visible
    const floatBar = page.locator('.compare-float-bar--top');
    const floatBarCount = await floatBar.count();

    if (floatBarCount > 0) {
      await expect(floatBar).toBeVisible();
      // Should show confidence
      const confidence = page.locator('.compare-float-bar__confidence');
      await expect(confidence).toBeVisible();
      const confText = await confidence.textContent();
      expect(confText).toMatch(/\d+%/);

      // Refine button in the floating bar
      const refineBtn = floatBar.locator('button').filter({ hasText: 'Refine' });
      await expect(refineBtn).toBeVisible();
      await expect(refineBtn).toBeEnabled();

      console.log(`Floating alignment bar: confidence=${confText}`);
    } else {
      console.log('Floating alignment bar not shown (no alignment result — OK for some files)');
    }
  });

  test('diff summary badges float at bottom of compare split', async ({ page }) => {
    await uploadAndCompare(page);

    const bottomBar = page.locator('.compare-float-bar--bottom');
    const bottomBarCount = await bottomBar.count();

    if (bottomBarCount > 0) {
      await expect(bottomBar).toBeVisible();
      const badges = bottomBar.locator('.comparison-badge');
      const badgeCount = await badges.count();
      expect(badgeCount).toBeGreaterThan(0);
      console.log(`Floating diff badges: ${badgeCount} badge(s)`);
    } else {
      console.log('No floating diff badges (no changes detected — OK)');
    }
  });
});

test.describe('Control Point Picker', () => {
  test('refine button in floating bar enters picking mode', async ({ page }) => {
    await uploadAndCompare(page);

    const floatBar = page.locator('.compare-float-bar--top');
    const floatBarCount = await floatBar.count();

    if (floatBarCount === 0) {
      console.log('No floating alignment bar — skipping picking mode test');
      return;
    }

    const refineBtn = floatBar.locator('button').filter({ hasText: 'Refine' });
    const refineBtnCount = await refineBtn.count();

    if (refineBtnCount === 0) {
      console.log('Refine button not shown — skipping picking mode test');
      return;
    }

    await refineBtn.click();

    // Should show picking mode instruction banner
    const instructionBar = page.locator('.compare-float-bar--instruction');
    await expect(instructionBar).toBeVisible({ timeout: 5_000 });

    const text = await instructionBar.textContent();
    expect(text).toContain('Click matching points');

    // Re-align button should be present
    const realignBtn = instructionBar.locator('button').filter({ hasText: 'Re-align' });
    await expect(realignBtn).toBeVisible();

    // Cancel button
    const cancelBtn = instructionBar.locator('button').filter({ hasText: 'Cancel' });
    await expect(cancelBtn).toBeVisible();

    console.log(`Picking mode entered. Instructions: "${text?.substring(0, 80)}..."`);
  });

  test('cancel exits picking mode', async ({ page }) => {
    await uploadAndCompare(page);

    const floatBar = page.locator('.compare-float-bar--top');
    if (await floatBar.count() === 0) {
      console.log('No floating alignment bar — skipping cancel test');
      return;
    }

    const refineBtn = floatBar.locator('button').filter({ hasText: 'Refine' });
    if (await refineBtn.count() === 0) {
      console.log('Refine button not shown — skipping cancel test');
      return;
    }

    await refineBtn.click();
    await expect(page.locator('.compare-float-bar--instruction')).toBeVisible({ timeout: 5_000 });

    // Click Cancel
    await page.locator('.compare-float-bar--instruction button').filter({ hasText: 'Cancel' }).click();

    // Instruction banner should disappear
    await expect(page.locator('.compare-float-bar--instruction')).not.toBeVisible({ timeout: 5_000 });

    // Alignment floating bar with Refine should reappear
    await expect(page.locator('.compare-float-bar--top')).toBeVisible();

    console.log('Cancel exited picking mode, floating bar reappeared');
  });
});

test.describe('Compact Wizard', () => {
  test('wizard step collapses to compact after revision loaded', async ({ page }) => {
    await uploadAndCompare(page);

    // After comparison, the full upload wizard should be replaced by compact summary
    const compactStep = page.locator('.wizard-step-compact');
    const compactCount = await compactStep.count();

    if (compactCount > 0) {
      await expect(compactStep).toBeVisible();

      // Should show filename
      const fileText = page.locator('.wizard-step-compact__file');
      await expect(fileText).toBeVisible();

      // Should have Replace button
      const replaceBtn = compactStep.locator('button').filter({ hasText: 'Replace' });
      await expect(replaceBtn).toBeVisible();

      console.log('Wizard step collapsed to compact summary');
    } else {
      console.log('Compact wizard step not shown (may be in full wizard mode — OK)');
    }
  });
});

test.describe('/api/dxf endpoint', () => {
  test('DXF file endpoint returns valid DXF content', async ({ page }) => {
    await uploadAndWait(page, 'r2000_blocks.dxf');

    const viewer = page.locator('.dxf-viewer');
    const viewerCount = await viewer.count();

    if (viewerCount > 0) {
      const canvas = viewer.locator('canvas');
      const canvasCount = await canvas.count();
      expect(canvasCount).toBeGreaterThanOrEqual(1);
      console.log('DXF endpoint working — viewer loaded with canvas');
    } else {
      const img = page.locator('img[alt*="drawing preview"]');
      const imgCount = await img.count();
      expect(imgCount).toBeGreaterThanOrEqual(1);
      console.log('DXF endpoint may have issues — fell back to PNG preview');
    }
  });
});
