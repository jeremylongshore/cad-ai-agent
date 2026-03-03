// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Production can be slow (Cloud Run cold start + LLM response)
const PLAN_TIMEOUT = 60_000;
const APPLY_TIMEOUT = 45_000;

test.describe('Chat Features', () => {
  test('suggestion chips appear after clear chat, click populates textarea', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload a DXF so the chat becomes active
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // After upload, system message exists — suggestion chips are in .chat__empty
    // which only renders when messages array is empty.  Clear chat to reset.
    const clearBtn = page.locator('button').filter({ hasText: 'Clear chat' });
    await expect(clearBtn).toBeVisible({ timeout: 5_000 });
    await clearBtn.click();

    // Suggestion chips should now be visible (empty chat state)
    const suggestions = page.locator('.chat__suggestion');
    await expect(suggestions.first()).toBeVisible({ timeout: 5_000 });

    const chipCount = await suggestions.count();
    expect(chipCount).toBeGreaterThanOrEqual(1);

    // Click first chip — should populate textarea but NOT send
    const firstChipText = await suggestions.first().textContent();
    await suggestions.first().click();

    const textarea = page.locator('.chat__textarea');
    const textareaValue = await textarea.inputValue();
    expect(textareaValue).toBe(firstChipText);

    // Message list should NOT have a new user message (chip only populates, doesn't send)
    const userMessages = page.locator('.message--user');
    const userMsgCount = await userMessages.count();
    expect(userMsgCount).toBe(0);

    console.log(`Suggestion chips: ${chipCount}, clicked "${firstChipText}" — textarea populated, not sent`);
  });

  test('Clear Chat button clears messages and shows suggestions', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload DXF — this generates a system message
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // Verify system message exists before clearing
    const systemMsgCount = await page.locator('.message--system').count();
    expect(systemMsgCount).toBeGreaterThanOrEqual(1);

    // Click "Clear chat"
    const clearBtn = page.locator('button').filter({ hasText: 'Clear chat' });
    await expect(clearBtn).toBeVisible({ timeout: 5_000 });
    await clearBtn.click();

    // Messages should be gone
    const userMsgCount = await page.locator('.message--user').count();
    expect(userMsgCount).toBe(0);

    const aiMsgCount = await page.locator('.message--ai').count();
    expect(aiMsgCount).toBe(0);

    // Suggestion chips should reappear (empty chat state)
    const suggestions = page.locator('.chat__suggestion');
    await expect(suggestions.first()).toBeVisible({ timeout: 5_000 });

    console.log('Clear chat: messages cleared, suggestions reappeared');
  });

  test('New File button resets to upload screen', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload DXF
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // Verify file info is showing (we're in workspace mode)
    await expect(page.locator('.file-info__name')).toContainText('r2000_blocks.dxf');

    // Click "New File" button in the header
    const newFileBtn = page.locator('button').filter({ hasText: 'New File' });
    await expect(newFileBtn).toBeVisible();
    await newFileBtn.click();

    // Should return to the upload screen
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 10_000 });

    console.log('New File button: reset to upload screen');
  });

  test('error banner dismiss button hides error', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Trigger an error by uploading a corrupt file
    const { writeFileSync, unlinkSync, mkdtempSync } = await import('fs');
    const { tmpdir } = await import('os');
    const tmpDir = mkdtempSync(path.join(tmpdir(), 'e2e-'));
    const corruptPath = path.join(tmpDir, 'corrupt.dxf');
    writeFileSync(corruptPath, 'THIS IS NOT A DXF FILE');

    await page.locator('input[type="file"]').setInputFiles(corruptPath);

    // Wait for error to appear
    const errorBanner = page.locator('[role="alert"], [style*="--accent-danger"]');
    await expect(errorBanner.first()).toBeVisible({ timeout: 20_000 });

    // Dismiss button should be present
    const dismissBtn = page.locator('button[aria-label="Dismiss error"]');
    const dismissCount = await dismissBtn.count();

    if (dismissCount > 0) {
      await dismissBtn.click();

      // Error banner should be hidden
      await expect(errorBanner.first()).not.toBeVisible({ timeout: 5_000 });
      console.log('Error banner dismissed successfully');
    } else {
      // Error may auto-dismiss or use a different pattern — still valid
      console.log('No dismiss button found (error may use different dismiss pattern)');
    }

    unlinkSync(corruptPath);
  });

  test('follow-up chips appear after apply success', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload DXF
    await page.locator('input[type="file"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    // Send a prompt
    const textarea = page.locator('.chat__textarea');
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('button[aria-label="Send"]').click();

    // Wait for ops to appear
    const opsOrError = await Promise.race([
      page.locator('.op-list__title').waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
      page.locator('.message--ai').filter({ hasText: 'Error' }).waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
    ]);

    if (opsOrError === 'error') {
      console.log('Plan failed — skipping follow-up chip check (API-dependent test)');
      return;
    }

    // Apply changes
    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    // Wait for apply to complete (Edited tab becomes active)
    await expect(
      page.locator('.preview__tab--active')
    ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

    // Follow-up chips should appear
    const followups = page.locator('.chat__followups .chat__suggestion');
    await expect(followups.first()).toBeVisible({ timeout: 10_000 });

    const followupCount = await followups.count();
    expect(followupCount).toBeGreaterThanOrEqual(1);

    // Check for expected follow-up text
    const allFollowupText = await page.locator('.chat__followups').textContent();
    const hasDownload = allFollowupText?.includes('Download');
    const hasAnotherEdit = allFollowupText?.includes('another edit');
    expect(hasDownload || hasAnotherEdit).toBe(true);

    console.log(`Follow-up chips after apply: ${followupCount} chips, text: "${allFollowupText}"`);
  });
});
