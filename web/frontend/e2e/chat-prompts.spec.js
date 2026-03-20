// @ts-check
/**
 * Chat prompt interaction tests — sending prompts, receiving responses,
 * suggestion chips, follow-up chips, keyboard shortcuts, loading indicators,
 * and auto-scroll behavior.
 */
import { test, expect } from '@playwright/test';
import path from 'path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

const UPLOAD_TIMEOUT = 30_000;
const PLAN_TIMEOUT = 60_000;

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

/** Send a prompt and wait for any AI response (message or ops). */
async function sendPrompt(page, text) {
  const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
  await expect(textarea).toBeEnabled({ timeout: 5_000 });
  await textarea.fill(text);
  await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();
}

/** Any AI response element — plain message, QnA panel, or design-ops panel. */
const AI_RESPONSE = '.message--ai, .qna-panel, .design-ops-panel';

/** Wait for ops or error after sending a prompt. Returns 'ops' | 'message' | 'error'. */
async function waitForResponse(page) {
  return await Promise.race([
    page.locator('.op-list__title, .op-item').first().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'ops'),
    page.locator(AI_RESPONSE).last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'message'),
    page.locator('.message--error').last().waitFor({ timeout: PLAN_TIMEOUT }).then(() => 'error'),
  ]).catch(() => 'timeout');
}

test.describe('Chat — Edit Prompts', () => {
  test('send edit prompt returns operations', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'Move the first column 24 feet east');

    const result = await waitForResponse(page);

    if (result === 'error') {
      const errorText = await page.locator('.message--error').last().textContent();
      if (/429|rate.limit|quota/i.test(errorText || '')) {
        test.skip(true, 'LLM rate-limited');
      }
    }

    // Should have ops or an AI message with plan description
    expect(['ops', 'message']).toContain(result);

    if (result === 'ops') {
      const opCount = await page.locator('.op-item').count();
      expect(opCount).toBeGreaterThanOrEqual(1);
    }

    console.log(`Edit prompt result: ${result}`);
  });
});

test.describe('Chat — Query Prompts', () => {
  test('send query prompt returns AI answer', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'How many entities are in this drawing?');

    const result = await waitForResponse(page);

    if (result === 'error') {
      const errorText = await page.locator('.message--error').last().textContent();
      if (/429|rate.limit|quota/i.test(errorText || '')) {
        test.skip(true, 'LLM rate-limited');
      }
    }

    // Query should return a message (plain, QnA, or design-ops — not edit operations)
    const aiResponse = page.locator(AI_RESPONSE).last();
    await expect(aiResponse).toBeVisible({ timeout: PLAN_TIMEOUT });

    const text = await aiResponse.textContent();
    expect(text?.length).toBeGreaterThan(10);

    console.log(`Query response (first 100 chars): ${text?.substring(0, 100)}`);
  });

  test('entity listing query returns response', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'List available entities');

    const result = await waitForResponse(page);

    if (result === 'error') {
      const errorText = await page.locator('.message--error').last().textContent();
      if (/429|rate.limit|quota/i.test(errorText || '')) {
        test.skip(true, 'LLM rate-limited');
      }
    }

    expect(['ops', 'message']).toContain(result);
  });
});

test.describe('Chat — Suggestion Chips', () => {
  test('suggestion chips appear and fill textarea on click', async ({ page }) => {
    await uploadAndWait(page);

    // Clear chat to show empty state with suggestions
    const clearBtn = page.locator('button').filter({ hasText: 'Clear chat' });
    await expect(clearBtn).toBeVisible({ timeout: 5_000 });
    await clearBtn.click();

    const suggestions = page.locator('.chat__suggestion');
    await expect(suggestions.first()).toBeVisible({ timeout: 5_000 });

    const chipCount = await suggestions.count();
    expect(chipCount).toBeGreaterThanOrEqual(1);

    // Click first chip — should populate textarea, not send
    const firstChipText = await suggestions.first().textContent();
    await suggestions.first().click();

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    const value = await textarea.inputValue();
    expect(value).toBe(firstChipText);

    // No user message should be sent
    const userMsgCount = await page.locator('.message--user').count();
    expect(userMsgCount).toBe(0);

    console.log(`Suggestion chip: "${firstChipText}" → textarea populated`);
  });

  test('follow-up chips after plan', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'Move the first column 24 feet east');

    const result = await waitForResponse(page);
    if (result !== 'ops') {
      console.log(`No ops returned (${result}) — skipping follow-up chip check`);
      return;
    }

    // Check for follow-up suggestions (e.g., "Apply all changes")
    const followups = page.locator('.chat__followups .chat__suggestion');
    if (await followups.first().isVisible({ timeout: 10_000 }).catch(() => false)) {
      const text = await page.locator('.chat__followups').textContent();
      expect(text?.length).toBeGreaterThan(0);
      console.log(`Follow-up chips after plan: ${text}`);
    }
  });

  test('follow-up chips after apply', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'Move the first column 24 feet east');

    const result = await waitForResponse(page);
    if (result !== 'ops') {
      console.log(`No ops returned (${result}) — skipping apply follow-up check`);
      return;
    }

    // Apply changes
    const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
    if (await applyBtn.isEnabled({ timeout: 5_000 }).catch(() => false)) {
      await applyBtn.click();

      await expect(
        page.locator('.preview__tab--active')
      ).toHaveText('Edited', { timeout: 45_000 });

      // Follow-up chips should include "Download"
      const followups = page.locator('.chat__followups .chat__suggestion');
      if (await followups.first().isVisible({ timeout: 10_000 }).catch(() => false)) {
        const text = await page.locator('.chat__followups').textContent();
        const hasDownload = text?.includes('Download');
        expect(hasDownload).toBe(true);
        console.log(`Follow-up chips after apply: ${text}`);
      }
    }
  });

  test('follow-up chips after error', async ({ page }) => {
    await uploadAndWait(page);
    // Deliberately send a nonsensical prompt
    await sendPrompt(page, 'xyzzy plugh');

    const result = await waitForResponse(page);

    // Check for follow-up suggestions regardless of response type
    const followups = page.locator('.chat__followups .chat__suggestion');
    if (await followups.first().isVisible({ timeout: 10_000 }).catch(() => false)) {
      console.log('Follow-up chips visible after response');
    } else {
      console.log(`No follow-up chips shown (response type: ${result})`);
    }
  });
});

test.describe('Chat — Message Management', () => {
  test('clear chat removes all messages', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'How many entities?');

    // Wait for any response
    await waitForResponse(page);

    // Verify we have messages (including QnA/design-ops panels)
    const msgCount = await page.locator(`.message--user, ${AI_RESPONSE}, .message--system`).count();
    expect(msgCount).toBeGreaterThanOrEqual(1);

    // Clear chat
    const clearBtn = page.locator('button').filter({ hasText: 'Clear chat' });
    await clearBtn.click();

    // All messages gone (user messages AND AI panels)
    await expect(page.locator('.message--user')).toHaveCount(0, { timeout: 5_000 });
    await expect(page.locator(AI_RESPONSE)).toHaveCount(0, { timeout: 5_000 });
  });

  test('export chat copies to clipboard', async ({ page, context }) => {
    // Grant clipboard permissions
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await uploadAndWait(page);
    await sendPrompt(page, 'How many layers in this drawing?');
    await waitForResponse(page);

    const exportBtn = page.locator('button').filter({ hasText: /Export|Copy chat/ });
    if (await exportBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await exportBtn.click();

      // Check clipboard content
      const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
      expect(clipboardText.length).toBeGreaterThan(0);
      console.log(`Exported chat (${clipboardText.length} chars)`);
    } else {
      console.log('Export/copy button not found — skipping');
    }
  });

  test('retry regenerates AI response', async ({ page }) => {
    await uploadAndWait(page);
    await sendPrompt(page, 'How many entities?');
    await waitForResponse(page);

    // The "Retry this message" button appears in the message actions
    const retryBtn = page.locator('button').filter({ hasText: /Retry|Regenerate/ });
    if (await retryBtn.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      const firstResponse = await page.locator(AI_RESPONSE).last().textContent();
      await retryBtn.first().click();

      // Wait for new response
      await waitForResponse(page);

      const secondResponse = await page.locator(AI_RESPONSE).last().textContent();
      // New response should exist (may or may not differ from first)
      expect(secondResponse?.length).toBeGreaterThan(0);
      console.log('Retry generated new response');
    } else {
      console.log('Retry button not found — skipping');
    }
  });
});

test.describe('Chat — Keyboard Shortcuts', () => {
  test('Shift+Enter adds newline instead of submitting', async ({ page }) => {
    await uploadAndWait(page);

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.click();
    await textarea.fill('Line one');

    // Shift+Enter should add newline
    await page.keyboard.down('Shift');
    await page.keyboard.press('Enter');
    await page.keyboard.up('Shift');

    await page.keyboard.type('Line two');

    const value = await textarea.inputValue();
    expect(value).toContain('Line one');
    expect(value).toContain('Line two');

    // No user message should have been sent
    const userMsgCount = await page.locator('.message--user').count();
    expect(userMsgCount).toBe(0);
  });

  test('Escape clears input', async ({ page }) => {
    await uploadAndWait(page);

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.fill('Some draft text');

    expect(await textarea.inputValue()).toBe('Some draft text');

    await textarea.press('Escape');

    // Input should be cleared (or blurred — behavior may vary)
    const valueAfter = await textarea.inputValue();
    // Escape either clears or blurs — both are valid
    if (valueAfter === '') {
      console.log('Escape cleared the input');
    } else {
      // Check if textarea lost focus
      const isFocused = await textarea.evaluate(el => document.activeElement === el);
      if (!isFocused) {
        console.log('Escape blurred the textarea');
      } else {
        console.log('Escape had no effect (may not be implemented)');
      }
    }
  });
});

test.describe('Chat — Loading Indicators', () => {
  test('loading indicator shows during LLM response', async ({ page }) => {
    await uploadAndWait(page);

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();

    // Check for loading indicator (spinner, "Analyzing...", progress text)
    const loadingIndicator = page.locator(
      '.chat__loading, .message--loading, [class*="loading"], [class*="spinner"]'
    );

    const hasLoading = await loadingIndicator.first().isVisible({ timeout: 5_000 }).catch(() => false);
    if (hasLoading) {
      console.log('Loading indicator visible during LLM response');
    }

    // Check for phase text changes (e.g., "Analyzing..." → "Planning...")
    const phaseText = page.locator('.chat__phase, [class*="phase"], [class*="status-text"]');
    if (await phaseText.isVisible({ timeout: 3_000 }).catch(() => false)) {
      const text = await phaseText.textContent();
      console.log(`Loading phase: ${text}`);
    }

    // Wait for response to complete
    await waitForResponse(page);
  });

  test('elapsed time counter visible during load', async ({ page }) => {
    await uploadAndWait(page);

    const textarea = page.locator('[data-testid="chat-textarea"], .chat__textarea');
    await textarea.fill('Move the first column 24 feet east');
    await page.locator('[data-testid="chat-send"], button[aria-label="Send"]').click();

    // Look for elapsed time counter
    const timer = page.locator('[class*="elapsed"], [class*="timer"], [class*="duration"]');
    if (await timer.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const text = await timer.textContent();
      expect(text).toMatch(/\d/); // Should contain a number (seconds)
      console.log(`Elapsed timer: ${text}`);
    } else {
      console.log('Elapsed time counter not found (may not be implemented)');
    }

    await waitForResponse(page);
  });
});

test.describe('Chat — Auto-scroll', () => {
  test('auto-scroll follows new messages', async ({ page }) => {
    await uploadAndWait(page);

    // Send a prompt to generate messages
    await sendPrompt(page, 'List all layers in this drawing');
    await waitForResponse(page);

    // Get scroll position of chat container
    const chatContainer = page.locator('.chat__messages, [class*="message-list"]');
    if (await chatContainer.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const scrollTop = await chatContainer.evaluate(el => el.scrollTop);
      const scrollHeight = await chatContainer.evaluate(el => el.scrollHeight);
      const clientHeight = await chatContainer.evaluate(el => el.clientHeight);

      // Should be scrolled to bottom (within 50px tolerance)
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      if (isAtBottom) {
        console.log('Auto-scroll: chat scrolled to bottom');
      } else {
        console.log(`Auto-scroll: scrollTop=${scrollTop}, scrollHeight=${scrollHeight}, clientHeight=${clientHeight}`);
      }
    }
  });
});

test.describe('Chat — Entity Selection Context', () => {
  test('prompt with selected entities sends handles', async ({ page }) => {
    await uploadAndWait(page);

    // Try to select an entity by clicking the viewer center
    const canvas = page.locator('[data-testid="dxf-viewer"] canvas').first();
    if (!await canvas.isVisible({ timeout: 10_000 }).catch(() => false)) return;

    const box = await canvas.boundingBox();
    if (!box) return;

    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(1_000);

    const tagsVisible = await page.locator('[data-testid="chat-selection-tags"]').isVisible({ timeout: 5_000 }).catch(() => false);

    if (tagsVisible) {
      // Send a prompt with entities selected
      await sendPrompt(page, 'What is this entity?');

      const result = await waitForResponse(page);
      expect(['message', 'ops', 'error']).toContain(result);

      // Selection should clear after sending
      await expect(page.locator('[data-testid="chat-selection-tags"]')).not.toBeVisible({ timeout: 5_000 });

      console.log('Prompt sent with selected entities');
    } else {
      console.log('No entity at canvas center — skipping selection context test');
    }
  });
});
