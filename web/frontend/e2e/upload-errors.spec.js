// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import os from 'os';

/**
 * Write a temp file with given content and extension.
 */
function writeTmpFile(name, content) {
  const p = path.join(os.tmpdir(), name);
  fs.writeFileSync(p, content);
  return p;
}

test.describe('Upload Errors', () => {
  test('rejects corrupt .dxf with clear error message', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Create a file that has .dxf extension but is not a real DXF
    const garbageDxf = writeTmpFile('corrupt.dxf', 'THIS IS NOT A DXF FILE — JUST GARBAGE BYTES');

    await page.locator('input[type="file"]').setInputFiles(garbageDxf);

    // Should show error
    const errorLocator = page.locator('[role="alert"], [style*="--accent-danger"]');
    await expect(errorLocator.first()).toBeVisible({ timeout: 20_000 });

    // Error must not leak internal details
    const errorText = await errorLocator.first().textContent();
    expect(errorText).not.toContain('Traceback');
    expect(errorText).not.toContain('ezdxf');

    fs.unlinkSync(garbageDxf);
  });

  test('rejects garbage .pdf with user-friendly error', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    const garbagePdf = writeTmpFile('corrupt.pdf', '%PDF-1.4 this is garbage not a real pdf at all');

    await page.locator('input[type="file"]').setInputFiles(garbagePdf);

    const errorLocator = page.locator('[role="alert"], [style*="--accent-danger"]');
    await expect(errorLocator.first()).toBeVisible({ timeout: 20_000 });

    const errorText = await errorLocator.first().textContent();
    expect(errorText).not.toContain('Traceback');
    expect(errorText).not.toContain('pip install');

    fs.unlinkSync(garbagePdf);
  });
});
