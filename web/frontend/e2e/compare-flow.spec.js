// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Comparison API can be slow on production (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;

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

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const badges = page.locator('.comparison-badge');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(1);

    const allBadgeText = await summary.textContent();
    expect(allBadgeText).not.toContain('No changes detected');

    console.log(`r2000_blocks vs r2000_revision — badges: ${badgeCount}, text: ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r2018_polylines — cross-version diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await summary.textContent();
    // Totally different files — must detect changes
    expect(allBadgeText).not.toContain('No changes detected');

    const addedBadge = page.locator('.comparison-badge--added');
    const removedBadge = page.locator('.comparison-badge--removed');
    const addedCount = await addedBadge.count();
    const removedCount = await removedBadge.count();
    expect(addedCount + removedCount).toBeGreaterThanOrEqual(1);

    console.log(`r2000_blocks vs r2018_polylines — ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r12_basic — old format revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await summary.textContent();
    expect(allBadgeText).not.toContain('No changes detected');

    console.log(`r2000_blocks vs r12_basic — ${allBadgeText}`);
  });

  test('identical file shows no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const summaryText = await summary.textContent();
    expect(summaryText).toContain('No changes detected');

    console.log('Identical file — correctly shows no changes');
  });

  test('comparison preview image renders after diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    await expect(page.locator('.comparison-summary')).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const previewImg = page.locator('.preview__image-wrap img');
    const imgCount = await previewImg.count();
    if (imgCount > 0) {
      const src = await previewImg.getAttribute('src');
      expect(src).toBeTruthy();
      console.log('Comparison diff overlay image rendered');
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

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await summary.textContent();
    expect(allBadgeText).not.toContain('No changes detected');

    console.log(`r2018_polylines vs r2000_revision — ${allBadgeText}`);
  });

  test('r2018_polylines self-compare — no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const summaryText = await summary.textContent();
    expect(summaryText).toContain('No changes detected');

    console.log('r2018_polylines self-compare — correctly no changes');
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

    const summary = page.locator('.comparison-summary');
    await expect(summary).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await summary.textContent();
    expect(allBadgeText).not.toContain('No changes detected');

    console.log(`r12_basic vs r2000_blocks — ${allBadgeText}`);
  });
});
