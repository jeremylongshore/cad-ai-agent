// @ts-check
/**
 * Multi-Turn Conversation E2E Tests — real Gemini, real DXF.
 *
 * Tests what real users actually do: follow-up questions, corrections,
 * drill-downs, error recovery, undo flows. Each conversation uploads
 * a DXF once, then sends multiple turns without reloading.
 *
 * Run: npm run e2e:conversations
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { scoreResponse } from './helpers/quality-scorer.js';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const CONVERSATIONS_PATH = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'realworld_conversations.json');
const RESULTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'realworld-conversations');
const SCREENSHOTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'screenshots');

const PROMPT_TIMEOUT = 120_000;
const APPLY_TIMEOUT = 45_000;

// Load conversations
let conversations = [];
try {
  conversations = JSON.parse(fs.readFileSync(CONVERSATIONS_PATH, 'utf-8'));
} catch (e) {
  console.warn('Could not load conversations file:', e.message);
}

// Ensure output directories exist
fs.mkdirSync(RESULTS_DIR, { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

/**
 * Resolve fixture path — handles both relative and absolute paths.
 */
function resolveFixture(fixturePath) {
  if (!fixturePath) return null;
  const resolved = fixturePath.startsWith('/')
    ? fixturePath
    : path.join(PROJECT_ROOT, fixturePath);
  return fs.existsSync(resolved) ? resolved : null;
}

test.describe('Multi-Turn Conversations (Gemini E2E)', () => {
  test.setTimeout(PROMPT_TIMEOUT * 5); // Each conversation has multiple turns

  for (const conv of conversations) {
    test(`${conv.id}: ${conv.title}`, async ({ page }) => {
      const fixturePath = resolveFixture(conv.drawing_fixture);
      if (!fixturePath) {
        test.skip(true, `Fixture not found: ${conv.drawing_fixture}`);
        return;
      }

      const turnResults = [];

      // 1. Navigate and upload
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      await page.locator('input[type="file"]').setInputFiles(fixturePath);
      await expect(
        page.locator('.message--system').filter({ hasText: 'Loaded' })
      ).toBeVisible({ timeout: 30_000 });

      // 2. Process each turn
      for (let i = 0; i < conv.turns.length; i++) {
        const turn = conv.turns[i];
        const turnStart = Date.now();

        // Intercept response
        let capturedResponse = null;
        await page.route('**/api/v2/prompt', async (route) => {
          const response = await route.fetch();
          try {
            capturedResponse = await response.json();
          } catch {
            capturedResponse = null;
          }
          await route.fulfill({ response });
        });

        // Send prompt
        const textarea = page.locator('.chat__textarea');
        await expect(textarea).toBeEnabled({ timeout: 10_000 });
        await textarea.fill(turn.prompt);
        await page.locator('button[aria-label="Send"]').click();

        // Wait for response
        const aiMessages = page.locator('.message--ai');
        const expectedCount = i + 1; // One AI message per turn
        const errorMessage = page.locator('.message--error').last();

        const outcome = await Promise.race([
          aiMessages.nth(expectedCount - 1).waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'ai'),
          errorMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'error'),
        ]).catch(() => 'timeout');

        // Screenshot after this turn
        await page.screenshot({
          path: path.join(SCREENSHOTS_DIR, `${conv.id}-turn${i + 1}.png`),
          fullPage: true,
        });

        // Handle rate limiting
        if (outcome === 'error') {
          const errorText = await errorMessage.textContent().catch(() => '');
          if (/429|rate.limit|quota/i.test(errorText || '')) {
            test.skip(true, `Rate-limited at turn ${i + 1}`);
            return;
          }
        }

        const response = capturedResponse || {};
        const ops = response.operations || [];
        const durationMs = Date.now() - turnStart;

        // Apply if requested
        if (turn.apply && ops.length > 0 && outcome === 'ai') {
          try {
            const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
            await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
            await applyBtn.click();
            await expect(
              page.locator('.preview__tab--active')
            ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

            await page.screenshot({
              path: path.join(SCREENSHOTS_DIR, `${conv.id}-turn${i + 1}-applied.png`),
              fullPage: true,
            });
          } catch (applyErr) {
            console.warn(`Apply failed at turn ${i + 1}: ${applyErr.message}`);
          }
        }

        // Record turn result
        turnResults.push({
          turn: i + 1,
          prompt: turn.prompt,
          expected_family: turn.expected_family,
          expected_behavior: turn.expected_behavior,
          outcome,
          response: {
            task_family: response.task_family,
            message: response.message,
            operations: ops,
          },
          duration_ms: durationMs,
          applied: turn.apply && ops.length > 0,
        });

        // Unroute for next turn
        await page.unroute('**/api/v2/prompt');

        // Tier 1: No crash
        expect(outcome, `Turn ${i + 1} crashed/timed out`).not.toBe('timeout');
      }

      // Save conversation record
      const record = {
        conversation_id: conv.id,
        title: conv.title,
        drawing_fixture: conv.drawing_fixture,
        turns: turnResults,
        total_duration_ms: turnResults.reduce((sum, t) => sum + t.duration_ms, 0),
        timestamp: new Date().toISOString(),
      };

      fs.writeFileSync(
        path.join(RESULTS_DIR, `${conv.id}.json`),
        JSON.stringify(record, null, 2) + '\n'
      );
    });
  }
});
