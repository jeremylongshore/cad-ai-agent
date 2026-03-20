// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Comparison / revision API can be slow (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;
const APPLY_TIMEOUT = 45_000;

/**
 * Upload a master DXF → navigate to Compare tab → upload a revision DXF.
 * Returns after the comparison result is visible (floating bar, ops list, or compact step).
 */
async function uploadMasterAndRevision(page, masterFile, revisionFile) {
  await page.goto('/');
  await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

  // Upload master
  await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, masterFile));
  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: 30_000 });

  // Switch to Compare tab
  const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
  await compareTab.click();
  await expect(compareTab).toHaveClass(/preview__tab--active/);

  // Upload revision
  const revisionInput = page.locator('input#revision-upload');
  await revisionInput.setInputFiles(path.join(DXF_ZOO, revisionFile));

  // Wait for any indicator that comparison completed:
  // floating bottom bar, ops list, or compact wizard step
  await expect(
    page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
  ).toBeVisible({ timeout: COMPARE_TIMEOUT });
}

test.describe('Revision Wizard', () => {
  test('upload revision shows alignment info (method + confidence)', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // Alignment info is now in the floating top bar
    const floatBarTop = page.locator('.compare-float-bar--top');
    await expect(floatBarTop).toBeVisible({ timeout: 5_000 });

    // Method badge inside the top floating bar
    const alignmentBadge = floatBarTop.locator('.badge').filter({
      hasText: /Identity|Translation|Rigid|Anchor|Feature|Manual/,
    });
    await expect(alignmentBadge.first()).toBeVisible({ timeout: 5_000 });

    // Confidence percentage rendered in the floating bar
    const confidenceEl = floatBarTop.locator('.compare-float-bar__confidence');
    const confidenceCount = await confidenceEl.count();
    if (confidenceCount > 0) {
      const confidenceText = await confidenceEl.textContent();
      expect(confidenceText).not.toBeNull();
      console.log(`Alignment confidence: ${confidenceText}`);
    }

    const methodText = await alignmentBadge.first().textContent();
    console.log(`Alignment method: ${methodText}`);
  });

  test('diff summary badges appear (added/removed/modified/moved)', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // Diff summary badges are now floating overlays in the bottom bar
    const floatBarBottom = page.locator('.compare-float-bar--bottom');
    await expect(floatBarBottom).toBeVisible({ timeout: 5_000 });

    const badges = floatBarBottom.locator('.comparison-badge');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(1);

    // At least one category badge should be present
    const addedCount = await floatBarBottom.locator('.comparison-badge--added').count();
    const removedCount = await floatBarBottom.locator('.comparison-badge--removed').count();
    const modifiedCount = await floatBarBottom.locator('.comparison-badge--modified').count();
    const movedCount = await floatBarBottom.locator('.comparison-badge--moved').count();
    const total = addedCount + removedCount + modifiedCount + movedCount;

    expect(total).toBeGreaterThanOrEqual(1);

    console.log(`Diff badges — added: ${addedCount}, removed: ${removedCount}, modified: ${modifiedCount}, moved: ${movedCount}`);
  });

  test('individual ops rendered with approve/reject buttons', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // Revision operation items should appear
    const opItems = page.locator('.revision-op-item');
    await expect(opItems.first()).toBeVisible({ timeout: 5_000 });

    const opCount = await opItems.count();
    expect(opCount).toBeGreaterThanOrEqual(1);

    // Each op item should have approve and reject buttons
    const firstOp = opItems.first();
    const approveBtn = firstOp.locator('button').filter({ hasText: 'Approve' });
    const rejectBtn = firstOp.locator('button').filter({ hasText: 'Reject' });
    await expect(approveBtn).toBeVisible();
    await expect(rejectBtn).toBeVisible();

    // Op type badge should be present
    const typeBadge = firstOp.locator('.op-item__type');
    await expect(typeBadge).toBeVisible();

    console.log(`Revision ops rendered: ${opCount} items with approve/reject buttons`);
  });

  test('Approve All → apply button enabled → apply → success', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // Wait for ops to load
    const opItems = page.locator('.revision-op-item');
    await expect(opItems.first()).toBeVisible({ timeout: 5_000 });

    // Click "Approve All"
    const approveAllBtn = page.locator('button').filter({ hasText: 'Approve All' });
    await expect(approveAllBtn).toBeVisible();
    await approveAllBtn.click();

    // Apply button should now be enabled (text pattern: "Apply N Approved Change(s)")
    const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    // Wait for bundle download to appear (indicates apply succeeded)
    const bundleDownload = page.locator('.bundle-download');
    await expect(bundleDownload).toBeVisible({ timeout: APPLY_TIMEOUT });

    // Status text should confirm success
    const statusText = await page.locator('.bundle-download__status').textContent();
    expect(statusText).toContain('successfully');

    console.log(`Apply succeeded: ${statusText}`);
  });

  test('bundle download button appears post-apply', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // Approve all and apply
    await expect(page.locator('.revision-op-item').first()).toBeVisible({ timeout: 5_000 });
    await page.locator('button').filter({ hasText: 'Approve All' }).click();

    const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    // Bundle download section
    const bundleDownload = page.locator('.bundle-download');
    await expect(bundleDownload).toBeVisible({ timeout: APPLY_TIMEOUT });

    // Download button present
    const downloadBtn = page.locator('button').filter({ hasText: 'Download Bundle' });
    await expect(downloadBtn).toBeVisible();

    // Hint text should explain bundle contents
    const hint = page.locator('.bundle-download__hint');
    await expect(hint).toBeVisible();

    console.log('Bundle download section rendered with download button and hint');
  });

  test('Refine button visible in floating alignment bar', async ({ page }) => {
    await uploadMasterAndRevision(page, 'r2000_blocks.dxf', 'r2000_revision.dxf');

    // "Refine" button (formerly "Refine Alignment") lives in the floating top bar
    const floatBarTop = page.locator('.compare-float-bar--top');
    await expect(floatBarTop).toBeVisible({ timeout: 5_000 });

    const refineBtn = floatBarTop.locator('button').filter({ hasText: 'Refine' });
    await expect(refineBtn).toBeVisible();

    console.log('Refine button visible in floating alignment bar');
  });

  test('profile selector visible with options', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload master
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // Switch to Compare tab
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    // Profile selector should be visible
    const profileSelect = page.locator('#profile-select');
    await expect(profileSelect).toBeVisible({ timeout: 5_000 });

    // Should have at least the default "All entities" option
    const options = profileSelect.locator('option');
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThanOrEqual(1);

    const firstOptionText = await options.first().textContent();
    expect(firstOptionText).toContain('All entities');

    // If "structural" profile exists, selecting it should show a hint
    if (optionCount > 1) {
      await profileSelect.selectOption({ index: 1 });
      const hint = page.locator('.input-group__hint');
      const hintCount = await hint.count();
      if (hintCount > 0) {
        const hintText = await hint.textContent();
        expect(hintText?.length).toBeGreaterThan(0);
        console.log(`Profile hint: ${hintText}`);
      }
    }

    console.log(`Profile selector: ${optionCount} option(s), first: "${firstOptionText}"`);
  });
});
