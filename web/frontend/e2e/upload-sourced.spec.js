// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

// Externally-sourced DXF files from open-source repos (see SOURCES.md)
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const SOURCED = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'sourced');

// Discover all .dxf files in the sourced directory
const files = fs.existsSync(SOURCED)
  ? fs.readdirSync(SOURCED).filter(f => f.endsWith('.dxf')).sort()
  : [];

test.describe('Upload Sourced DXF Files', () => {
  // Guard: skip entire suite if no sourced files exist
  test.skip(files.length === 0, 'No sourced DXF files found — run scripts/download_sourced_fixtures.sh');

  for (const file of files) {
    test(`uploads sourced ${file}`, async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles(path.join(SOURCED, file));

      // Wait for either successful load OR a graceful error
      const outcome = await Promise.race([
        page.locator('.message--system').filter({ hasText: 'Loaded' })
          .waitFor({ timeout: 30_000 }).then(() => 'loaded'),
        page.locator('[role="alert"]')
          .waitFor({ timeout: 30_000 }).then(() => 'error'),
      ]);

      if (outcome === 'loaded') {
        // Success path: verify file info and entity count
        await expect(page.locator('.file-info__name')).toContainText(file);

        const entityStat = page.locator('.file-info__stat-value').first();
        const entityText = await entityStat.textContent();
        expect(Number(entityText)).toBeGreaterThanOrEqual(0);

        console.log(`[ok] ${file} — loaded, ${entityText} entities`);
      } else {
        // Graceful error path: backend rejected file, no internal traceback
        const alertEl = page.locator('[role="alert"]');
        const alertText = await alertEl.textContent();

        // Should NOT expose raw Python tracebacks or 500 errors
        expect(alertText).not.toMatch(/Traceback|Internal Server Error|500/);

        console.log(`[error] ${file} — graceful rejection: ${alertText?.slice(0, 100)}`);
      }
    });
  }
});
