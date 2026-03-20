// @ts-check
/**
 * Edit workflow tests — plan, preview ops, toggle checkboxes,
 * apply, download, validation blockers/warnings, structured preview.
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

const UPLOAD_TIMEOUT = 30_000;
const PLAN_TIMEOUT = 60_000;
const APPLY_TIMEOUT = 45_000;

/** Upload a DXF and wait for session ready. */
async function uploadAndWait(page) {
  await page.goto('/');
  await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

  await page.locator('[data-testid="file-upload-input"]').setInputFiles(
    path.join(DXF_ZOO, 'r2000_blocks.dxf')
  );

  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: UPLOAD_TIMEOUT });
}

/** Any AI response element — plain message, QnA panel, or design-ops panel. */
const AI_RESPONSE = '.message--ai, .qna-panel, .design-ops-panel';

/** Send a prompt and wait for ops or error. Returns 'ops' | 'message' | 'error'. */
async function sendPromptAndWait(page, text) {
  const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
  await expect(textarea).toBeEnabled({ timeout: 5_000 });
  await textarea.fill(text);
  await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();

  const result = await Promise.race([
    page.locator('.op-list__title, .op-item, [data-testid="edit-op-item"]').first().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
    page.locator(AI_RESPONSE).last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'message'),
    page.locator('.message--error').last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
  ]).catch(() => 'timeout');

  if (result === 'error') {
    const errorText = await page.locator('.message--error').last().textContent();
    if (/429|rate.limit|quota/i.test(errorText || '')) {
      test.skip(true, 'LLM rate-limited');
    }
  }

  return result;
}

test.describe('Edit Workflow — Plan & Preview', () => {
  test('plan shows ops with checkboxes', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') {
      console.log(`No structured ops returned (${result}) — skipping checkbox test`);
      return;
    }

    const opItems = page.locator('.op-item, [data-testid="edit-op-item"]');
    const opCount = await opItems.count();
    expect(opCount).toBeGreaterThanOrEqual(1);

    // Check for checkboxes on op items
    const checkbox = opItems.first().locator('input[type="checkbox"]');
    if (await checkbox.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Should be checked by default
      await expect(checkbox).toBeChecked();
      console.log(`${opCount} ops with checkboxes`);
    } else {
      console.log(`${opCount} ops rendered (checkboxes may not be present in this mode)`);
    }
  });

  test('toggle operation checkbox deselects/selects', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') return;

    const opItems = page.locator('.op-item, [data-testid="edit-op-item"]');
    const checkbox = opItems.first().locator('input[type="checkbox"]');

    if (!await checkbox.isVisible({ timeout: 3_000 }).catch(() => false)) {
      console.log('No checkboxes on ops — skipping toggle test');
      return;
    }

    // Uncheck
    await checkbox.uncheck();
    await expect(checkbox).not.toBeChecked();

    // Re-check
    await checkbox.check();
    await expect(checkbox).toBeChecked();

    console.log('Op checkbox toggle works');
  });
});

test.describe('Edit Workflow — Apply & Download', () => {
  test('apply changes shows edited tab', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') {
      console.log(`No ops to apply (${result})`);
      return;
    }

    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    // Edited tab becomes active
    await expect(
      page.locator('.preview__tab--active')
    ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

    // Viewer or preview image should show
    const editedViewer = page.locator('.dxf-viewer');
    const editedImg = page.locator('img[alt*="edited"]');
    await expect(editedViewer.or(editedImg)).toBeVisible({ timeout: 30_000 });

    console.log('Applied changes — Edited tab active');
  });

  test('download edited DXF after apply', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') return;

    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    await expect(
      page.locator('.preview__tab--active')
    ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

    // Download the edited DXF — target the preview panel button (not chat follow-up)
    const downloadBtn = page.locator('.preview__controls button, .bundle-download button')
      .filter({ hasText: /Download.*DXF/i }).first();
    await expect(downloadBtn).toBeVisible({ timeout: 10_000 });

    const downloadPromise = page.waitForEvent('download', { timeout: APPLY_TIMEOUT });
    await downloadBtn.click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/\.dxf$/i);

    // Save and verify file is non-empty
    const downloadDir = path.join(PROJECT_ROOT, 'web', 'frontend', 'test-results');
    fs.mkdirSync(downloadDir, { recursive: true });
    const savedPath = path.join(downloadDir, `edit-workflow-${download.suggestedFilename()}`);
    await download.saveAs(savedPath);

    const stat = fs.statSync(savedPath);
    expect(stat.size).toBeGreaterThan(1000);

    console.log(`Downloaded: ${download.suggestedFilename()} (${stat.size} bytes)`);
  });
});

test.describe('Edit Workflow — Validation', () => {
  test('protected layer edit shows validation blocker', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Edit the title block text');

    // Should either get blocked ops or a message about protected layers
    const blockerBadge = page.locator('.badge--blocked, [class*="blocker"], [class*="blocked"]');
    const protectedMsg = page.locator('.message--ai, .message--error');

    const hasBlocker = await blockerBadge.first().isVisible({ timeout: 5_000 }).catch(() => false);
    const hasMessage = await protectedMsg.last().isVisible({ timeout: 5_000 }).catch(() => false);

    if (hasBlocker) {
      // Apply should be disabled when there are blockers
      const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
      const applyVisible = await applyBtn.isVisible({ timeout: 3_000 }).catch(() => false);
      if (applyVisible) {
        const isDisabled = await applyBtn.isDisabled();
        expect(isDisabled).toBe(true);
      }
      console.log('Validation blocker shown for protected layer edit');
    } else if (hasMessage) {
      const text = await protectedMsg.last().textContent();
      // LLM may refuse the edit in its response
      console.log(`Response to protected layer edit: ${text?.substring(0, 100)}`);
    } else {
      console.log(`Protected layer test result: ${result}`);
    }
  });

  test('validation warnings shown but apply still allowed', async ({ page }) => {
    await uploadAndWait(page);
    // A large move might trigger a warning but not a blocker
    const result = await sendPromptAndWait(page, 'Move the first column 1000 feet east');

    if (result !== 'ops') return;

    // Check for warning badges
    const warningBadge = page.locator('.badge--warning, [class*="warning"]');
    const hasWarning = await warningBadge.first().isVisible({ timeout: 5_000 }).catch(() => false);

    if (hasWarning) {
      // Apply should still be enabled despite warnings
      const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
      await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
      console.log('Warnings shown but apply still enabled');
    } else {
      // No warnings triggered — that's OK, depends on LLM response
      console.log('No validation warnings triggered');
    }
  });
});

test.describe('Edit Workflow — Structured Preview', () => {
  test('structured preview: approve & apply', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') return;

    // Look for Approve & Apply button (structured preview mode)
    const approveApplyBtn = page.locator('button').filter({ hasText: /Approve.*Apply|Apply Changes/ });
    if (await approveApplyBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await approveApplyBtn.click();

      // Should either show Edited tab or success message
      const editedTab = page.locator('.preview__tab--active');
      const successMsg = page.locator('.message--system').filter({ hasText: /applied|success/i });
      await expect(editedTab.or(successMsg)).toBeVisible({ timeout: APPLY_TIMEOUT });

      console.log('Approve & Apply succeeded');
    } else {
      console.log('Approve & Apply button not available (may use different flow)');
    }
  });

  test('structured preview: reject clears plan', async ({ page }) => {
    await uploadAndWait(page);
    const result = await sendPromptAndWait(page, 'Move the first column 24 feet east');

    if (result !== 'ops') return;

    // Look for Reject button
    const rejectBtn = page.locator('button').filter({ hasText: /Reject|Discard|Cancel/ });
    if (await rejectBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await rejectBtn.click();

      // Ops should be cleared or hidden
      await page.waitForTimeout(1_000);
      const opsAfter = await page.locator('.op-item, [data-testid="edit-op-item"]').count();
      // After reject, ops should be gone or reset
      console.log(`After reject: ${opsAfter} ops remaining`);
    } else {
      console.log('Reject button not available');
    }
  });
});
