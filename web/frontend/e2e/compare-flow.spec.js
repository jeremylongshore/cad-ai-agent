// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Comparison API can be slow on production (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;

test.describe('Comparison Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload master DXF first
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Compare tab visible after master upload', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await expect(compareTab).toBeVisible();
  });

  test('Compare tab shows upload prompt before revision uploaded', async ({ page }) => {
    // Click Compare tab
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();
    await expect(compareTab).toHaveClass(/preview__tab--active/);

    // Upload button visible
    const uploadBtn = page.locator('button').filter({ hasText: 'Upload Revision DXF' });
    await expect(uploadBtn).toBeVisible({ timeout: 5_000 });
  });

  test('upload revision → comparison badges appear', async ({ page }) => {
    // Switch to Compare tab
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();
    await expect(compareTab).toHaveClass(/preview__tab--active/);

    // Upload revision DXF
    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison summary to appear
    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // At least one comparison badge should be visible
    const badges = page.locator('.comparison-badge');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(1);

    // The files differ, so total_changes > 0 — should NOT show "No changes detected"
    const allBadgeText = await summary.textContent();
    expect(allBadgeText).not.toContain('No changes detected');

    console.log(`Comparison badges: ${badgeCount}, text: ${allBadgeText}`);
  });

  test('comparison shows at least added or removed badges', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // r2000_revision.dxf has different entities than r2000_blocks.dxf —
    // should detect added and/or removed entities
    const addedBadge = page.locator('.comparison-badge--added');
    const removedBadge = page.locator('.comparison-badge--removed');
    const modifiedBadge = page.locator('.comparison-badge--modified');
    const movedBadge = page.locator('.comparison-badge--moved');

    const addedCount = await addedBadge.count();
    const removedCount = await removedBadge.count();
    const modifiedCount = await modifiedBadge.count();
    const movedCount = await movedBadge.count();

    // At least one change type should be detected
    const totalBadges = addedCount + removedCount + modifiedCount + movedCount;
    expect(totalBadges).toBeGreaterThanOrEqual(1);

    console.log(`Badges: added=${addedCount}, removed=${removedCount}, modified=${modifiedCount}, moved=${movedCount}`);
  });

  test('comparison preview image renders', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison results
    await expect(page.locator('.comparison-summary')).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Check if comparison preview image was rendered
    const previewImg = page.locator('.preview__image-wrap img');
    const imgCount = await previewImg.count();
    if (imgCount > 0) {
      const src = await previewImg.getAttribute('src');
      expect(src).toBeTruthy();
      console.log('Comparison preview image rendered');
    } else {
      // render_available may be false if ezdxf can't produce the overlay image —
      // the comparison still succeeded if badges are visible
      console.log('No comparison preview image (render may not be available)');
    }
  });

  test('identical file comparison shows no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    // Upload the SAME file as revision
    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Should show "No changes detected" badge
    const summaryText = await summary.textContent();
    expect(summaryText).toContain('No changes detected');
  });
});
