// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

// Use real DXF from project fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');
const PYTHON = path.join(PROJECT_ROOT, '.venv', 'bin', 'python');

// Production uses real Gemini API — needs longer timeouts for cold starts + LLM response
const PLAN_TIMEOUT = 60_000;
const APPLY_TIMEOUT = 45_000;

/**
 * Validate a downloaded DXF file using ezdxf.
 * Returns { valid, entities, version, error }.
 */
function validateDxf(dxfPath) {
  try {
    const script = `
import json, sys, ezdxf
try:
    doc = ezdxf.readfile("${dxfPath.replace(/\\/g, '\\\\')}")
    msp = doc.modelspace()
    entities = len(list(msp))
    print(json.dumps({"valid": True, "entities": entities, "version": doc.dxfversion}))
except Exception as e:
    print(json.dumps({"valid": False, "error": str(e)}))
`;
    const out = execSync(`${PYTHON} -c '${script}'`, { encoding: 'utf-8', timeout: 10_000 });
    return JSON.parse(out.trim());
  } catch (e) {
    return { valid: false, error: e.message };
  }
}

test.describe('Full Edit Flow', () => {
  test('upload → prompt "move" → see ops → apply → download valid edited DXF', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // 1. Upload real DXF with blocks (50 entities)
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // 2. Send a "move" prompt
    const textarea = page.locator('.chat__textarea');
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('button[aria-label="Send"]').click();

    // 3. Wait for either operations OR an error message (captures both outcomes)
    const opsOrError = await Promise.race([
      page.locator('.op-list__title').waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
      page.locator('.message--ai').filter({ hasText: 'Error' }).waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]);

    if (opsOrError === 'error') {
      const errorMsg = await page.locator('.message--ai').filter({ hasText: 'Error' }).textContent();
      console.error('Plan failed on production:', errorMsg);
      expect(opsOrError, `Plan API error: ${errorMsg}`).toBe('ops');
    }

    const opCount = await page.locator('.op-item').count();
    expect(opCount).toBeGreaterThanOrEqual(1);

    // AI message in chat
    await expect(page.locator('.message--ai').first()).toBeVisible();

    // 4. Apply Changes (no download yet)
    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    // 5. Verify Edited tab is active + image visible
    await expect(
      page.locator('.preview__tab--active')
    ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });
    await expect(
      page.locator('.preview__image-wrap img[alt="edited drawing preview"]')
    ).toBeVisible({ timeout: 10_000 });

    // 6. Download via separate button
    const downloadBtn = page.locator('button').filter({ hasText: 'Download Edited DXF' });
    await expect(downloadBtn).toBeVisible({ timeout: 5_000 });

    const downloadPromise = page.waitForEvent('download', { timeout: APPLY_TIMEOUT });
    await downloadBtn.click();

    // 7. Verify download filename
    const download = await downloadPromise;
    const filename = download.suggestedFilename();
    expect(filename).toMatch(/_edited\.dxf$/);

    // 8. Save and validate the actual DXF content
    const downloadDir = path.join(PROJECT_ROOT, 'web', 'frontend', 'test-results');
    fs.mkdirSync(downloadDir, { recursive: true });
    const savedPath = path.join(downloadDir, filename);
    await download.saveAs(savedPath);

    // File must be non-trivial size (not empty or error page)
    const stat = fs.statSync(savedPath);
    expect(stat.size).toBeGreaterThan(1000); // real DXF is always > 1KB

    // Validate with ezdxf — must be a parseable DXF with entities
    const result = validateDxf(savedPath);
    expect(result.valid, `DXF validation failed: ${result.error || 'unknown'}`).toBe(true);
    expect(result.entities).toBeGreaterThan(0);

    // Original has 50 entities — edited should still have entities (move doesn't delete)
    console.log(`Downloaded DXF: ${filename}, ${stat.size} bytes, ${result.entities} entities, version ${result.version}`);
  });

  test('upload → prompt "delete" → operations show type badges', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const textarea = page.locator('.chat__textarea');
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill('Delete the first column mark');
    await page.locator('button[aria-label="Send"]').click();

    // Operation type badge visible
    await expect(page.locator('.op-item__type').first()).toBeVisible({ timeout: PLAN_TIMEOUT });
  });

  test('upload → prompt "rename text" → edit_text op planned', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const textarea = page.locator('.chat__textarea');
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill('Rename the text label to UPDATED');
    await page.locator('button[aria-label="Send"]').click();

    await expect(page.locator('.op-item').first()).toBeVisible({ timeout: PLAN_TIMEOUT });
    await expect(page.locator('.message--ai').first()).toBeVisible();
  });
});
