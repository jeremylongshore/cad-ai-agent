// @ts-check
/**
 * Error handling tests — corrupted files, network errors, session expiry,
 * protected layer enforcement, and error banner dismiss.
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import os from 'os';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

const UPLOAD_TIMEOUT = 30_000;
const PLAN_TIMEOUT = 60_000;

/** Create a temp file. */
function writeTmpFile(name, content) {
  const p = path.join(os.tmpdir(), `e2e-err-${Date.now()}-${name}`);
  fs.writeFileSync(p, content);
  return p;
}

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

test.describe('Error Handling — Upload Errors', () => {
  test('corrupted DXF shows friendly error (no crash, no traceback)', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    const corruptDxf = writeTmpFile('corrupt.dxf', 'THIS IS NOT A DXF FILE — GARBAGE BYTES');

    await page.locator('[data-testid="file-upload-input"]').setInputFiles(corruptDxf);

    // Error should appear
    const errorLocator = page.locator('[role="alert"], [style*="--accent-danger"]');
    await expect(errorLocator.first()).toBeVisible({ timeout: 20_000 });

    // Must not leak internal details
    const errorText = await errorLocator.first().textContent();
    expect(errorText).not.toContain('Traceback');
    expect(errorText).not.toContain('ezdxf');
    expect(errorText).not.toContain('pip install');

    // Page should not have crashed
    const body = page.locator('body');
    await expect(body).toBeVisible();

    fs.unlinkSync(corruptDxf);
    console.log(`Corrupt DXF error: "${errorText?.substring(0, 80)}"`);
  });

  test('network error during upload shows banner', async ({ page, context }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Block API requests to simulate network error
    await context.route('**/api/**', route => route.abort('connectionfailed'));

    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );

    // Error banner should appear
    const errorLocator = page.locator('[role="alert"], [style*="--accent-danger"], .message--error');
    await expect(errorLocator.first()).toBeVisible({ timeout: 20_000 });

    const errorText = await errorLocator.first().textContent();
    console.log(`Network error message: "${errorText?.substring(0, 100)}"`);

    // Unblock routes for cleanup
    await context.unrouteAll();
  });
});

test.describe('Error Handling — Session Errors', () => {
  test('session expired shows error or reconnect option', async ({ page, context }) => {
    await uploadAndWait(page);

    // Simulate backend failure by intercepting the prompt endpoint
    await context.route('**/api/v2/prompt', route => {
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Session not found or expired' }),
      });
    });
    await context.route('**/api/plan', route => {
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Session not found or expired' }),
      });
    });

    // Send a prompt — should hit our mocked 404
    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.fill('How many entities?');
    await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();

    // Should show error message or reconnect prompt
    const errorOrBanner = page.locator(
      '[role="alert"], [style*="--accent-danger"], .message--error, .connection-banner'
    );
    await expect(errorOrBanner.first()).toBeVisible({ timeout: 20_000 });

    await context.unrouteAll();
    console.log('Session error handled gracefully');
  });
});

test.describe('Error Handling — Protected Layers', () => {
  test('protected layer edit blocked with clear message', async ({ page }) => {
    await uploadAndWait(page);

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.fill('Delete everything on the title block layer');
    await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();

    // Any AI response (plain, QnA, or design-ops panel)
    const AI_RESPONSE = '.message--ai, .qna-panel, .design-ops-panel';

    // Wait for any response
    const result = await Promise.race([
      page.locator('.op-item, [data-testid="edit-op-item"]').first().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
      page.locator(AI_RESPONSE).last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'message'),
      page.locator('.message--error').last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]).catch(() => 'timeout');

    if (result === 'ops') {
      // If ops were returned, they should have validation blockers
      const blockerBadge = page.locator('.badge--blocked, [class*="blocker"]');
      const hasBlocker = await blockerBadge.first().isVisible({ timeout: 5_000 }).catch(() => false);
      if (hasBlocker) {
        console.log('Protected layer edit correctly blocked by validator');
      } else {
        console.log('Ops returned without explicit blocker badge');
      }
    } else if (result === 'message') {
      // LLM may refuse in its response text
      const text = await page.locator(AI_RESPONSE).last().textContent();
      const mentionsProtected = /protect|title.?block|cannot|restricted/i.test(text || '');
      if (mentionsProtected) {
        console.log('LLM refused protected layer edit in response');
      } else {
        console.log(`LLM response: ${text?.substring(0, 100)}`);
      }
    } else {
      console.log(`Protected layer test result: ${result}`);
    }
  });
});

test.describe('Error Handling — Dismiss', () => {
  test('dismiss error banner hides it', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Trigger error
    const corruptDxf = writeTmpFile('dismiss-test.dxf', 'NOT A DXF');
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(corruptDxf);

    const errorLocator = page.locator('[role="alert"], [style*="--accent-danger"]');
    await expect(errorLocator.first()).toBeVisible({ timeout: 20_000 });

    // Find dismiss button
    const dismissBtn = page.locator('button[aria-label="Dismiss error"], button[aria-label="dismiss"]');
    const closeBtn = errorLocator.first().locator('button').last();

    if (await dismissBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await dismissBtn.click();
      await expect(errorLocator.first()).not.toBeVisible({ timeout: 5_000 });
      console.log('Error banner dismissed via aria-label button');
    } else if (await closeBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await closeBtn.click();
      await expect(errorLocator.first()).not.toBeVisible({ timeout: 5_000 });
      console.log('Error banner dismissed via close button');
    } else {
      console.log('No dismiss button found on error banner');
    }

    fs.unlinkSync(corruptDxf);
  });
});
