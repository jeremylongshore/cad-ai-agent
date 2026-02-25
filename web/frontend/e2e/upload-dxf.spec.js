// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real DXF files from the project's test fixtures (no generation step)
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

test.describe('DXF Upload', () => {
  test('uploads r2000_blocks.dxf — file info + preview + system message', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    // System message confirms load
    const systemMsg = page.locator('.message--system');
    await expect(systemMsg).toContainText('Loaded r2000_blocks.dxf', { timeout: 20_000 });

    // File info sidebar
    await expect(page.locator('.file-info__name')).toContainText('r2000_blocks.dxf');

    // Entity count > 0
    const entityStat = page.locator('.file-info__stat-value').first();
    const entityText = await entityStat.textContent();
    expect(Number(entityText)).toBeGreaterThan(0);

    // Layer badges visible
    await expect(page.locator('.badge').first()).toBeVisible();

    // Preview image rendered
    const previewImg = page.locator('img[alt*="drawing preview"]');
    const imgCount = await previewImg.count();
    if (imgCount > 0) {
      const src = await previewImg.getAttribute('src');
      expect(src).toBeTruthy();
    }
  });

  test('uploads r12_basic.dxf — older format loads OK', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));

    await expect(page.locator('.message--system')).toContainText('Loaded r12_basic.dxf', { timeout: 20_000 });
    await expect(page.locator('.file-info__name')).toContainText('r12_basic.dxf');
  });

  test('uploads r2018_polylines.dxf — modern format loads OK', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    await expect(page.locator('.message--system')).toContainText('Loaded r2018_polylines.dxf', { timeout: 20_000 });
    await expect(page.locator('.file-info__name')).toContainText('r2018_polylines.dxf');
  });
});
