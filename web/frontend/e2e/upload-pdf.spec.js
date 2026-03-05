// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real PDFs from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const PDF_DIR = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'test_pdfs');

test.describe('PDF Upload', () => {
  test('uploads simple_geometry.pdf — succeeds or gives user-friendly error', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(PDF_DIR, 'simple_geometry.pdf'));

    // Wait for either success or error (PDF conversion can be slow)
    const result = await Promise.race([
      page.locator('.message--system').filter({ hasText: 'Loaded' }).waitFor({ timeout: 30_000 }).then(() => 'success'),
      page.locator('[role="alert"]').waitFor({ timeout: 30_000 }).then(() => 'error'),
    ]);

    if (result === 'success') {
      await expect(page.locator('.upload-bar-compact__filename')).toBeVisible();
    } else {
      const errorText = await page.locator('[role="alert"]').textContent();
      // Must be user-friendly — no internal tracebacks
      expect(errorText).not.toContain('pip install');
      expect(errorText).not.toContain('Traceback');
      expect(errorText).not.toContain('ModuleNotFoundError');
    }
  });

  test('uploads structural_plan.pdf — larger file handles OK', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(PDF_DIR, 'structural_plan.pdf'));

    const result = await Promise.race([
      page.locator('.message--system').filter({ hasText: 'Loaded' }).waitFor({ timeout: 30_000 }).then(() => 'success'),
      page.locator('[role="alert"]').waitFor({ timeout: 30_000 }).then(() => 'error'),
    ]);

    if (result === 'success') {
      await expect(page.locator('.upload-bar-compact__filename')).toBeVisible();
      const metaText = await page.locator('.upload-bar-compact__meta').textContent();
      expect(metaText).toMatch(/\d+\s+entities/);
    } else {
      const errorText = await page.locator('[role="alert"]').textContent();
      expect(errorText).not.toContain('Traceback');
      expect(errorText).not.toContain('pip install');
    }
  });
});
