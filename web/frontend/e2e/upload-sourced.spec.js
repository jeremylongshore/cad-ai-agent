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

// Split files into batches to avoid Firebase Auth rate-limiting.
// Each batch shares a single page/auth session via test.step().
const BATCH_SIZE = 8;
const batches = [];
for (let i = 0; i < files.length; i += BATCH_SIZE) {
  batches.push(files.slice(i, i + BATCH_SIZE));
}

test.describe('Upload Sourced DXF Files', () => {
  test.skip(files.length === 0, 'No sourced DXF files — run scripts/download_sourced_fixtures.sh');

  for (let batchIdx = 0; batchIdx < batches.length; batchIdx++) {
    const batch = batches[batchIdx];

    test(`sourced upload batch ${batchIdx + 1} (${batch[0]}…${batch[batch.length - 1]})`, async ({ page }) => {
      // Auth once for the entire batch
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 30_000 });

      for (const file of batch) {
        await test.step(`upload ${file}`, async () => {
          // Navigate fresh for each file (reuses same auth session)
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
            await expect(page.locator('.upload-bar-compact__filename')).toContainText(file);
            const metaText = await page.locator('.upload-bar-compact__meta').textContent();
            expect(metaText).toMatch(/\d+\s+entities/);
            console.log(`  [ok] ${file} — loaded, ${metaText}`);
          } else {
            const alertText = await page.locator('[role="alert"]').textContent();
            expect(alertText).not.toMatch(/Traceback|Internal Server Error|500/);
            console.log(`  [error] ${file} — graceful rejection: ${alertText?.slice(0, 100)}`);
          }
        });
      }
    });
  }
});
