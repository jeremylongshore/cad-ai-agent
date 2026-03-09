// @ts-check
/**
 * Production Canary Tests — 20 critical prompts against real Gemini.
 *
 * Runs against production (TARGET=production) or local. Tests one prompt
 * per major capability to verify the system is alive and correct.
 *
 * Run: npm run e2e:canary
 * Prod: TARGET=production npm run e2e:canary
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { scoreResponse } from './helpers/quality-scorer.js';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const CANARY_PATH = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'realworld_canary.json');
const RESULTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'canary-results');
const SCREENSHOTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'screenshots');

// Canary fixture — small committed DXF that's always available
const CANARY_FIXTURE = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r2000_blocks.dxf');

const PROMPT_TIMEOUT = 120_000;

// Load canary prompts
let canaryPrompts = [];
try {
  canaryPrompts = JSON.parse(fs.readFileSync(CANARY_PATH, 'utf-8'));
} catch (e) {
  console.warn('Could not load canary prompts:', e.message);
}

// Ensure output directories
fs.mkdirSync(RESULTS_DIR, { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

test.describe('Production Canary (Gemini E2E)', () => {
  test.setTimeout(PROMPT_TIMEOUT);

  for (const prompt of canaryPrompts) {
    test(`canary: ${prompt.id} — ${prompt.prompt.slice(0, 50)}`, async ({ page }) => {
      const startTime = Date.now();

      if (!fs.existsSync(CANARY_FIXTURE)) {
        test.skip(true, `Canary fixture not found: ${CANARY_FIXTURE}`);
        return;
      }

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

      // Navigate and upload
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      await page.locator('input[type="file"]').setInputFiles(CANARY_FIXTURE);
      await expect(
        page.locator('.message--system').filter({ hasText: 'Loaded' })
      ).toBeVisible({ timeout: 30_000 });

      // Send prompt
      const textarea = page.locator('.chat__textarea');
      await expect(textarea).toBeEnabled({ timeout: 5_000 });
      await textarea.fill(prompt.prompt);
      await page.locator('button[aria-label="Send"]').click();

      // Wait for response
      const aiMessage = page.locator('.message--ai').last();
      const errorMessage = page.locator('.message--error').last();

      const outcome = await Promise.race([
        aiMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'ai'),
        errorMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'error'),
      ]).catch(() => 'timeout');

      // Screenshot
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `canary-${prompt.id}.png`),
        fullPage: true,
      });

      // Handle rate limiting
      if (outcome === 'error') {
        const errorText = await errorMessage.textContent().catch(() => '');
        if (/429|rate.limit|quota/i.test(errorText || '')) {
          test.skip(true, 'LLM rate-limited — transient 429');
          return;
        }
      }

      const response = capturedResponse || {};
      const ops = response.operations || [];
      const durationMs = Date.now() - startTime;

      // Save result
      const record = {
        prompt_id: prompt.id,
        source_id: prompt.source_id,
        prompt: prompt.prompt,
        category: prompt.category,
        outcome,
        response: {
          task_family: response.task_family,
          message: response.message,
          operations: ops,
        },
        quality: scoreResponse(prompt, response),
        duration_ms: durationMs,
        timestamp: new Date().toISOString(),
      };

      fs.writeFileSync(
        path.join(RESULTS_DIR, `${prompt.id}.json`),
        JSON.stringify(record, null, 2) + '\n'
      );

      // Assertions — canary tests are strict
      expect(outcome, `Canary ${prompt.id} crashed/timed out`).toBe('ai');

      if (prompt.expected_behavior === 'produces_ops') {
        expect(ops.length, `Canary ${prompt.id}: expected ops`).toBeGreaterThanOrEqual(1);
      }
      if (prompt.must_not_produce_ops) {
        expect(ops.length, `Canary ${prompt.id}: expected no ops`).toBe(0);
      }
      if (prompt.expected_behavior === 'answer_only' || prompt.expected_behavior === 'report') {
        expect(
          (response.message?.length || 0) > 0,
          `Canary ${prompt.id}: expected message`
        ).toBe(true);
      }
    });
  }
});
