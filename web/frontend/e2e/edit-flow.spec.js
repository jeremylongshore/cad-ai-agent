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

/**
 * Compare two DXF files semantically using ezdxf.
 * Returns entity counts, INSERT positions (as [x,y] rounded to 2dp), and TEXT values for both.
 */
function compareDxf(originalPath, editedPath) {
  try {
    const script = `
import json, ezdxf

def extract(path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    entities = list(msp)
    inserts = []
    texts = []
    for e in entities:
        if e.dxftype() == "INSERT":
            pos = e.dxf.insert
            inserts.append([round(pos.x, 2), round(pos.y, 2)])
        elif e.dxftype() in ("TEXT", "MTEXT"):
            t = e.dxf.text if e.dxftype() == "TEXT" else e.text
            texts.append(t)
    return {"count": len(entities), "inserts": inserts, "insert_count": len(inserts), "texts": texts, "text_count": len(texts)}

orig = extract("${originalPath.replace(/\\/g, '\\\\')}")
edited = extract("${editedPath.replace(/\\/g, '\\\\')}")
print(json.dumps({"original": orig, "edited": edited}))
`;
    const out = execSync(`${PYTHON} -c '${script}'`, { encoding: 'utf-8', timeout: 10_000 });
    return JSON.parse(out.trim());
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Apply changes and download the edited DXF file.
 * Returns the local path where the downloaded file was saved.
 */
async function applyAndDownload(page, filenamePrefix = '') {
  const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
  await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
  await applyBtn.click();

  await expect(
    page.locator('.preview__tab--active')
  ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

  const downloadBtn = page.locator('button.btn').filter({ hasText: 'Download Edited DXF' });
  await expect(downloadBtn).toBeVisible({ timeout: 5_000 });

  const downloadPromise = page.waitForEvent('download', { timeout: APPLY_TIMEOUT });
  await downloadBtn.click();
  const download = await downloadPromise;

  const downloadDir = path.join(PROJECT_ROOT, 'web', 'frontend', 'test-results');
  fs.mkdirSync(downloadDir, { recursive: true });
  const savedPath = path.join(downloadDir, `${filenamePrefix}${download.suggestedFilename()}`);
  await download.saveAs(savedPath);
  return savedPath;
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
      page.locator('.message--ai').filter({ hasText: /Error|error|429|rate.limit/i }).waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]);

    if (opsOrError === 'error') {
      const errorMsg = await page.locator('.message--ai').last().textContent();
      if (/429|rate.limit|quota/i.test(errorMsg || '')) {
        test.skip(true, 'LLM rate-limited — transient 429');
      }
      console.error('Plan failed on production:', errorMsg);
      expect(opsOrError, `Plan API error: ${errorMsg}`).toBe('ops');
    }

    const opCount = await page.locator('.op-item').count();
    expect(opCount).toBeGreaterThanOrEqual(1);

    // AI message in chat
    await expect(page.locator('.message--ai').first()).toBeVisible();

    // 4. Apply + download + verify edited preview image
    const savedPath = await applyAndDownload(page);
    await expect(
      page.locator('.preview__image-wrap img[alt="edited drawing preview"]')
    ).toBeVisible({ timeout: 10_000 });

    // 5. Validate the actual DXF content
    const stat = fs.statSync(savedPath);
    expect(stat.size).toBeGreaterThan(1000); // real DXF is always > 1KB

    const result = validateDxf(savedPath);
    expect(result.valid, `DXF validation failed: ${result.error || 'unknown'}`).toBe(true);
    expect(result.entities).toBeGreaterThan(0);

    // Semantic validation: compare original vs edited DXF
    const originalPath = path.join(DXF_ZOO, 'r2000_blocks.dxf');
    const cmp = compareDxf(originalPath, savedPath);
    expect(cmp.error).toBeUndefined();

    // Move preserves entity count (doesn't add or delete)
    expect(cmp.edited.count).toBe(cmp.original.count);
    // Move preserves INSERT count
    expect(cmp.edited.insert_count).toBe(cmp.original.insert_count);
    // At least one INSERT position must differ (the moved entity)
    const origPositions = new Set(cmp.original.inserts.map(p => p.join(',')));
    const editedPositions = new Set(cmp.edited.inserts.map(p => p.join(',')));
    const allSame = [...editedPositions].every(p => origPositions.has(p));
    expect(allSame, 'Move should change at least one INSERT position').toBe(false);

    console.log(`Downloaded DXF: ${path.basename(savedPath)}, ${stat.size} bytes, ${result.entities} entities, version ${result.version}`);
    console.log(`Move validation: ${cmp.original.count} → ${cmp.edited.count} entities, position changed: ${!allSame}`);
  });

  test('upload → prompt "delete" → apply → download → fewer entities', async ({ page }) => {
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

    // Wait for ops or error
    const opsOrError = await Promise.race([
      page.locator('.op-item__type').first().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
      page.locator('.message--ai').filter({ hasText: /Error|error|429|rate.limit/i }).waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]);

    if (opsOrError === 'error') {
      const errorMsg = await page.locator('.message--ai').last().textContent();
      if (/429|rate.limit|quota/i.test(errorMsg || '')) {
        test.skip(true, 'LLM rate-limited — transient 429');
      }
      expect(opsOrError, `Plan API error: ${errorMsg}`).toBe('ops');
    }

    // Apply + download
    const savedPath = await applyAndDownload(page, 'delete_');

    // Semantic validation: entity count decreased
    const originalPath = path.join(DXF_ZOO, 'r2000_blocks.dxf');
    const cmp = compareDxf(originalPath, savedPath);
    expect(cmp.error).toBeUndefined();

    expect(cmp.edited.count).toBeLessThan(cmp.original.count);
    // LLM may delete the block INSERT or its TEXT label — either count should decrease
    const fewerInserts = cmp.edited.insert_count < cmp.original.insert_count;
    const fewerTexts = cmp.edited.text_count < cmp.original.text_count;
    expect(fewerInserts || fewerTexts, 'Delete should remove at least one INSERT or TEXT').toBe(true);

    console.log(`Delete validation: ${cmp.original.count} → ${cmp.edited.count} entities, inserts ${cmp.original.insert_count} → ${cmp.edited.insert_count}, texts ${cmp.original.text_count} → ${cmp.edited.text_count}`);
  });

  test('upload → prompt "rename text" → apply → download → text changed', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const textarea = page.locator('.chat__textarea');
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill('Rename text label B00 to UPDATED');
    await page.locator('button[aria-label="Send"]').click();

    // Wait for ops or error
    const opsOrError = await Promise.race([
      page.locator('.op-item').first().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
      page.locator('.message--ai').filter({ hasText: /Error|error|429|rate.limit/i }).waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]);

    if (opsOrError === 'error') {
      const errorMsg = await page.locator('.message--ai').last().textContent();
      if (/429|rate.limit|quota/i.test(errorMsg || '')) {
        test.skip(true, 'LLM rate-limited — transient 429');
      }
      expect(opsOrError, `Plan API error: ${errorMsg}`).toBe('ops');
    }

    await expect(page.locator('.message--ai').first()).toBeVisible();

    // Apply + download
    const savedPath = await applyAndDownload(page, 'edittext_');

    // Semantic validation: text content changed
    const originalPath = path.join(DXF_ZOO, 'r2000_blocks.dxf');
    const cmp = compareDxf(originalPath, savedPath);
    expect(cmp.error).toBeUndefined();

    // edit_text preserves entity count (no add/delete)
    expect(cmp.edited.count).toBe(cmp.original.count);
    // At least one TEXT value differs
    const origTexts = new Set(cmp.original.texts);
    const textsIdentical = cmp.edited.texts.length === cmp.original.texts.length
      && cmp.edited.texts.every(t => origTexts.has(t));
    expect(textsIdentical, 'edit_text should change at least one TEXT value').toBe(false);
    // The word "UPDATED" should appear in some text entity (case-insensitive)
    const hasUpdated = cmp.edited.texts.some(t => t.toUpperCase().includes('UPDATED'));
    expect(hasUpdated, 'Edited text should contain "UPDATED"').toBe(true);

    console.log(`Edit text validation: ${cmp.original.count} → ${cmp.edited.count} entities, texts changed: ${!textsIdentical}, has UPDATED: ${hasUpdated}`);
  });
});
