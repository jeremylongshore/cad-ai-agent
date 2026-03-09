// @ts-check
/**
 * Real-World Profile Journey E2E Tests — 25 AEC personas against real Gemini.
 *
 * Each test simulates a real AEC professional: uploads their specific document
 * (DXF or PDF), runs their multi-turn conversation, captures responses,
 * screenshots, and traces, then asserts correctness.
 *
 * Run: npm run e2e:profiles
 * Single: REALWORLD=1 npx playwright test --grep "profile-01"
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { scoreResponse } from './helpers/quality-scorer.js';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const PROFILES_PATH = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'realworld_profile_conversations.json');
const RESULTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'profile-results');
const SCREENSHOTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'screenshots');
const BACKEND_URL = 'http://localhost:8322';

const PROMPT_TIMEOUT = 120_000;
const APPLY_TIMEOUT = 45_000;

// Load profile conversations
let profiles = [];
try {
  profiles = JSON.parse(fs.readFileSync(PROFILES_PATH, 'utf-8'));
} catch (e) {
  console.warn('Could not load profile conversations:', e.message);
}

// Ensure output directories
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

test.describe('Real-World Profile Journeys (Gemini E2E)', () => {
  // Each profile has 3-5 turns × 120s
  test.setTimeout(PROMPT_TIMEOUT * 6);

  for (const profile of profiles) {
    test(`${profile.id}: ${profile.title}`, async ({ page }) => {
      const fixturePath = resolveFixture(profile.drawing_fixture);
      if (!fixturePath) {
        test.skip(true, `Fixture not found: ${profile.drawing_fixture}`);
        return;
      }

      const turnResults = [];

      // 1. Navigate and upload
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      await page.locator('input[type="file"][accept*=".pdf"]').setInputFiles(fixturePath);
      await expect(
        page.locator('.message--system').filter({ hasText: 'Loaded' })
      ).toBeVisible({ timeout: 30_000 });

      // Screenshot after upload
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `${profile.id}-loaded.png`),
        fullPage: true,
      });

      // 2. Process each turn
      for (let i = 0; i < profile.turns.length; i++) {
        const turn = profile.turns[i];
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
        const expectedCount = i + 1;
        const errorMessage = page.locator('.message--error').last();

        const outcome = await Promise.race([
          aiMessages.nth(expectedCount - 1).waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'ai'),
          errorMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'error'),
        ]).catch(() => 'timeout');

        // Screenshot after turn
        await page.screenshot({
          path: path.join(SCREENSHOTS_DIR, `${profile.id}-turn${i + 1}.png`),
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

        // Apply if requested and ops produced
        if (turn.apply && ops.length > 0 && outcome === 'ai') {
          try {
            const applyBtn = page.locator('button').filter({ hasText: 'Apply Changes' });
            await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
            await applyBtn.click();
            await expect(
              page.locator('.preview__tab--active')
            ).toHaveText('Edited', { timeout: APPLY_TIMEOUT });

            await page.screenshot({
              path: path.join(SCREENSHOTS_DIR, `${profile.id}-turn${i + 1}-applied.png`),
              fullPage: true,
            });
          } catch (applyErr) {
            console.warn(`[${profile.id}] Apply failed at turn ${i + 1}: ${applyErr.message}`);
          }
        }

        // Score response quality
        const quality = scoreResponse(turn, response);

        // Behavior assertions
        let behaviorMatch = false;
        if (turn.expected_behavior === 'produces_ops') {
          behaviorMatch = ops.length >= 1;
        } else if (turn.expected_behavior === 'answer_only' || turn.expected_behavior === 'report') {
          behaviorMatch = (response.message?.length || 0) > 0;
        } else if (turn.expected_behavior === 'needs_clarification') {
          behaviorMatch = true;
        } else {
          behaviorMatch = outcome === 'ai';
        }

        // Record turn result
        turnResults.push({
          turn: i + 1,
          prompt: turn.prompt,
          expected_family: turn.expected_family,
          expected_behavior: turn.expected_behavior,
          outcome,
          behavior_match: behaviorMatch,
          family_match: response.task_family === turn.expected_family,
          response: {
            task_family: response.task_family,
            response_type: response.response_type,
            message: response.message,
            operations: ops,
            risk_level: response.risk_level,
          },
          quality,
          duration_ms: durationMs,
          applied: turn.apply && ops.length > 0,
        });

        // Unroute for next turn
        await page.unroute('**/api/v2/prompt');

        // Tier 1: No crash/timeout
        expect(outcome, `[${profile.id}] Turn ${i + 1} crashed/timed out`).not.toBe('timeout');

        // Tier 2: Behavior match
        if (turn.expected_behavior === 'produces_ops') {
          expect(ops.length, `[${profile.id}] Turn ${i + 1}: expected ops`).toBeGreaterThanOrEqual(1);
        }
        if (turn.expected_behavior === 'answer_only' || turn.expected_behavior === 'report') {
          expect(
            (response.message?.length || 0) > 0,
            `[${profile.id}] Turn ${i + 1}: expected message`
          ).toBe(true);
        }
      }

      // Save profile result record
      const record = {
        profile_id: profile.id,
        title: profile.title,
        role: profile.profile?.role,
        drawing_fixture: profile.drawing_fixture,
        turns: turnResults,
        summary: {
          total_turns: turnResults.length,
          passed: turnResults.filter(t => t.outcome === 'ai' && t.behavior_match).length,
          failed: turnResults.filter(t => t.outcome !== 'ai' || !t.behavior_match).length,
          total_duration_ms: turnResults.reduce((sum, t) => sum + t.duration_ms, 0),
        },
        timestamp: new Date().toISOString(),
      };

      fs.writeFileSync(
        path.join(RESULTS_DIR, `${profile.id}.json`),
        JSON.stringify(record, null, 2) + '\n'
      );
    });
  }
});
