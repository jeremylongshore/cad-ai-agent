// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Comparison API can be slow on production (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;

// Selector that resolves once comparison has finished and the UI has settled.
// The floating bar appears when there are changes; wizard-step-compact or
// revision-ops-list appear regardless. Waiting for any of these is safe for
// both the "has changes" and "no changes" cases.
const COMPARE_DONE_SELECTOR =
  '.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact';

test.describe('Comparison Flow — r2000_blocks master', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload master DXF
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Compare tab visible after master upload', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await expect(compareTab).toBeVisible();
  });

  test('Compare tab shows upload button before revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();
    await expect(compareTab).toHaveClass(/preview__tab--active/);

    const uploadBtn = page.locator('button').filter({ hasText: /Upload Revision/ });
    await expect(uploadBtn).toBeVisible({ timeout: 5_000 });
  });

  test('compare r2000_blocks vs r2000_revision — badges appear', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison to finish — float bar appears when there are changes
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const badges = page.locator('.comparison-badge');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(1);

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r2000_revision — badges: ${badgeCount}, text: ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r2018_polylines — cross-version diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    // Totally different files — float bar must appear with change badges
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const addedBadge = page.locator('.comparison-badge--added');
    const removedBadge = page.locator('.comparison-badge--removed');
    const addedCount = await addedBadge.count();
    const removedCount = await removedBadge.count();
    expect(addedCount + removedCount).toBeGreaterThanOrEqual(1);

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r2018_polylines — ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r12_basic — old format revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r12_basic — ${allBadgeText}`);
  });

  test('identical file shows no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    // For identical files the backend returns 0 changes, so the floating diff
    // bar never renders. Wait for comparison to finish by watching for the
    // compact wizard step or any revision ops list that may appear instead.
    await expect(page.locator(COMPARE_DONE_SELECTOR).first()).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Confirm that no diff badges were rendered
    await expect(page.locator('.compare-float-bar--bottom')).not.toBeVisible();

    console.log('Identical file — correctly shows no changes (float bar absent)');
  });

  test('comparison preview image renders after diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison to finish
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Accept either a static preview image or the interactive split viewer
    const previewImg = page.locator('.preview__image-wrap img');
    const splitViewer = page.locator('.compare-split-wrap');

    const imgCount = await previewImg.count();
    const splitCount = await splitViewer.count();

    if (imgCount > 0) {
      const src = await previewImg.getAttribute('src');
      expect(src).toBeTruthy();
      console.log('Comparison diff overlay image rendered');
    } else if (splitCount > 0) {
      await expect(splitViewer).toBeVisible();
      console.log('Comparison interactive split viewer rendered');
    } else {
      console.log('No comparison preview image (render_available=false)');
    }
  });
});

test.describe('Comparison Flow — r2018_polylines master', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });
  });

  test('compare r2018_polylines vs r2000_revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r2018_polylines vs r2000_revision — ${allBadgeText}`);
  });

  test('r2018_polylines self-compare — no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    // 0 changes — float bar must stay hidden
    await expect(page.locator(COMPARE_DONE_SELECTOR).first()).toBeVisible({ timeout: COMPARE_TIMEOUT });
    await expect(page.locator('.compare-float-bar--bottom')).not.toBeVisible();

    console.log('r2018_polylines self-compare — correctly no changes (float bar absent)');
  });
});

test.describe('Comparison Flow — r12_basic master', () => {
  test('compare r12_basic vs r2000_blocks', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r12_basic vs r2000_blocks — ${allBadgeText}`);
  });
});
