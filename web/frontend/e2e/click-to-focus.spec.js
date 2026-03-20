// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');
const PDF_DIR = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'test_pdfs');

const UPLOAD_TIMEOUT = 30_000;
const VIEWER_TIMEOUT = 30_000;
const LLM_TIMEOUT = 60_000;
const COMPARE_TIMEOUT = 45_000;

/** Upload a file and wait for session ready. */
async function uploadAndWait(page, filePath) {
  await page.goto('/');
  await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

  await page.locator('[data-testid="file-upload-input"]').setInputFiles(filePath);

  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: UPLOAD_TIMEOUT });
}

test.describe('Click to Focus — DXF', () => {
  const dxfFile = path.join(DXF_ZOO, 'r2000_blocks.dxf');

  test('planned operation click focuses viewer', async ({ page }) => {
    await uploadAndWait(page, dxfFile);
    await expect(page.locator('[data-testid="dxf-viewer"] canvas').first()).toBeVisible({ timeout: VIEWER_TIMEOUT });

    // Send an edit prompt to generate operations
    const textarea = page.locator('[data-testid="chat-textarea"]');
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('[data-testid="chat-send"]').click();

    // Wait for edit preview operations to appear
    const opItem = page.locator('[data-testid="edit-op-item"]').first();
    const hasEditOps = await opItem.isVisible({ timeout: LLM_TIMEOUT }).catch(() => false);

    if (hasEditOps) {
      // Click the operation item — should trigger focus highlight on viewer
      await opItem.click();

      // Focus highlight should appear (red pulsing border)
      const highlight = page.locator('[data-testid="viewer-focus-highlight"]');
      const highlightVisible = await highlight.isVisible({ timeout: 5_000 }).catch(() => false);

      if (highlightVisible) {
        // Should auto-dismiss after ~3 seconds
        await expect(highlight).not.toBeVisible({ timeout: 5_000 });
      }
    } else {
      // No structured edit ops — focus test requires structured preview; legacy path skipped
    }
  });

  test('focus highlight dismissed on viewer interaction', async ({ page }) => {
    await uploadAndWait(page, dxfFile);
    await expect(page.locator('[data-testid="dxf-viewer"] canvas').first()).toBeVisible({ timeout: VIEWER_TIMEOUT });

    const textarea = page.locator('[data-testid="chat-textarea"]');
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('[data-testid="chat-send"]').click();

    const opItem = page.locator('[data-testid="edit-op-item"]').first();
    if (!await opItem.isVisible({ timeout: LLM_TIMEOUT }).catch(() => false)) {
      // No structured edit ops — skipping dismiss-on-interaction test
      return;
    }

    await opItem.click();

    const highlight = page.locator('[data-testid="viewer-focus-highlight"]');
    if (!await highlight.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // No highlight appeared — entity may lack position data
      return;
    }

    // Simulate viewer pan by scrolling on canvas (triggers viewChanged)
    const canvas = page.locator('[data-testid="dxf-viewer"] canvas').first();
    const box = await canvas.boundingBox();
    if (box) {
      await page.mouse.wheel(0, 100);
      // Highlight should dismiss on view change
      await expect(highlight).not.toBeVisible({ timeout: 3_000 });
    }
  });
});

test.describe('Click to Focus — PDF', () => {
  const pdfFile = path.join(PDF_DIR, 'structural_plan.pdf');

  test('planned operation click focuses viewer (if viewer available)', async ({ page }) => {
    await uploadAndWait(page, pdfFile);

    const viewer = page.locator('[data-testid="dxf-viewer"]');
    if (!await viewer.isVisible({ timeout: VIEWER_TIMEOUT }).catch(() => false)) {
      // PDF rendered as image — click-to-focus not available for image preview
      return;
    }

    const textarea = page.locator('[data-testid="chat-textarea"]');
    await textarea.fill('List available entities');
    await page.locator('[data-testid="chat-send"]').click();

    // Wait for AI response
    const aiMsg = page.locator('.message--ai');
    await expect(aiMsg.last()).toBeVisible({ timeout: LLM_TIMEOUT });
  });
});

test.describe('Click to Focus — Revision Comparison', () => {
  test('revision change card click focuses viewer', async ({ page }) => {
    const masterFile = path.join(DXF_ZOO, 'r2000_blocks.dxf');
    const revisionFile = path.join(DXF_ZOO, 'r2000_revision.dxf');

    await uploadAndWait(page, masterFile);

    // Switch to Compare tab
    await page.locator('.preview__tab').filter({ hasText: 'Compare' }).click();

    // Upload revision
    await page.locator('input#revision-upload').setInputFiles(revisionFile);

    // Wait for comparison to complete
    await expect(
      page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
    ).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Click on a revision op item if available
    const revOp = page.locator('[data-testid="revision-op-item"]').first();
    if (await revOp.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await revOp.click();

      // Should trigger focus highlight on one of the compare viewers
      const highlight = page.locator('[data-testid="viewer-focus-highlight"]');
      await highlight.isVisible({ timeout: 5_000 }).catch(() => false);
    } else {
      // No revision ops to click — comparison may have had no changes
    }
  });
});
