// @ts-check
/**
 * Real-World Prompt E2E Tests — 118 prompts against real Gemini API.
 *
 * Each test uploads a real DXF, sends a real prompt through the full pipeline
 * (intent classification → LLM planning → validation), captures the response,
 * screenshots, and OTel traces, then asserts correctness.
 *
 * Run: npm run e2e:realworld
 * Single: npx playwright test --grep "rw-move-001"
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { scoreResponse } from './helpers/quality-scorer.js';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const PROMPTS_PATH = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'realworld_prompts.json');
const RESULTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'realworld-responses');
const SCREENSHOTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'screenshots');
const BACKEND_URL = 'http://localhost:8322';

// Timeout: 120s per prompt (Gemini cold start + LLM reasoning + validation)
const PROMPT_TIMEOUT = 120_000;

// Fixture name → real file path mapping
const FIXTURE_MAP = {
  structural: path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r2000_blocks.dxf'),
  overlapping: path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r2018_polylines.dxf'),
  empty_layers: path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r12_basic.dxf'),
  residential: path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r2000_blocks.dxf'),
  unicode: path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'r2000_blocks.dxf'),
};

/**
 * Resolve fixture path from prompt definition.
 * Handles both legacy fixture names and explicit file paths.
 */
function resolveFixture(promptDef) {
  const fixture = promptDef.drawing_fixture;
  if (fixture && fixture.includes('/')) {
    // Explicit path
    const resolved = path.join(PROJECT_ROOT, fixture);
    if (fs.existsSync(resolved)) return resolved;
  }
  return FIXTURE_MAP[fixture] || FIXTURE_MAP.structural;
}

// Load prompts
const prompts = JSON.parse(fs.readFileSync(PROMPTS_PATH, 'utf-8'));

// Ensure output directories exist
fs.mkdirSync(RESULTS_DIR, { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

test.describe('Real-World Prompts (Gemini E2E)', () => {
  // Generous timeout for real LLM calls
  test.setTimeout(PROMPT_TIMEOUT);

  for (const promptDef of prompts) {
    test(`${promptDef.id}: ${promptDef.prompt.slice(0, 60)}`, async ({ page }) => {
      const startTime = Date.now();
      const fixturePath = resolveFixture(promptDef);

      // Skip if fixture doesn't exist
      if (!fs.existsSync(fixturePath)) {
        test.skip(true, `Fixture not found: ${fixturePath}`);
        return;
      }

      // 1. Clear previous OTel traces
      try {
        await fetch(`${BACKEND_URL}/api/debug/traces`, { method: 'DELETE' });
      } catch {
        // Debug routes may not be available — non-fatal
      }

      // 2. Intercept v2/prompt response
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

      // 3. Navigate and upload fixture
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      await page.locator('input[type="file"][accept*=".pdf"]').setInputFiles(fixturePath);
      await expect(
        page.locator('.message--system').filter({ hasText: 'Loaded' })
      ).toBeVisible({ timeout: 30_000 });

      // Screenshot after load
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `${promptDef.id}-loaded.png`),
        fullPage: true,
      });

      // 4. Send prompt
      const textarea = page.locator('.chat__textarea');
      await expect(textarea).toBeEnabled({ timeout: 5_000 });
      await textarea.fill(promptDef.prompt);
      await page.locator('button[aria-label="Send"]').click();

      // 5. Wait for response — either AI message or error
      const aiMessage = page.locator('.message--ai').last();
      const errorMessage = page.locator('.message--error').last();

      const outcome = await Promise.race([
        aiMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'ai'),
        errorMessage.waitFor({ timeout: PROMPT_TIMEOUT }).then(() => 'error'),
      ]).catch(() => 'timeout');

      // Screenshot after response
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `${promptDef.id}-response.png`),
        fullPage: true,
      });

      // 6. Collect OTel traces
      let traces = [];
      try {
        const traceResp = await fetch(`${BACKEND_URL}/api/debug/traces`);
        if (traceResp.ok) {
          const traceData = await traceResp.json();
          traces = traceData.spans || [];
        }
      } catch {
        // Non-fatal
      }

      // 7. Extract UI state
      let uiOpCount = 0;
      let uiMessageText = '';
      try {
        uiOpCount = await page.locator('.op-item').count();
        uiMessageText = await aiMessage.textContent() || '';
      } catch {
        // May not be visible if error/timeout
      }

      // 8. Build response record
      const durationMs = Date.now() - startTime;
      const response = capturedResponse || {};

      const quality = scoreResponse(promptDef, response);

      // Tier 1: No crash, no 500
      const noCrash = outcome !== 'timeout' && outcome !== 'error';

      // Tier 2: Behavior match
      let behaviorMatch = false;
      const ops = response.operations || [];

      if (promptDef.expected_behavior === 'produces_ops') {
        behaviorMatch = ops.length >= 1;
      } else if (promptDef.expected_behavior === 'needs_clarification') {
        if (promptDef.must_not_produce_ops) {
          behaviorMatch = ops.length === 0;
        } else {
          behaviorMatch = true; // Clarification is acceptable
        }
      } else if (promptDef.expected_behavior === 'answer_only' || promptDef.expected_behavior === 'report') {
        behaviorMatch = (response.message?.length || 0) > 0;
      } else {
        behaviorMatch = noCrash; // Unknown behavior — just check no crash
      }

      // Tier 3: Family match (recorded, not hard fail)
      const familyMatch = response.task_family === promptDef.expected_family;

      // Tier 3: Op types match (recorded, not hard fail)
      const expectedOpTypes = new Set(promptDef.expected_op_types || []);
      const actualOpTypes = new Set(ops.map(o => o.op_type));
      const opTypesMatch = expectedOpTypes.size === 0 ||
        [...expectedOpTypes].every(t => actualOpTypes.has(t));

      const record = {
        prompt_id: promptDef.id,
        prompt: promptDef.prompt,
        category: promptDef.category,
        drawing_fixture: promptDef.drawing_fixture,
        expected_family: promptDef.expected_family,
        expected_behavior: promptDef.expected_behavior,
        response: {
          task_family: response.task_family,
          response_type: response.response_type,
          message: response.message || uiMessageText,
          operations: ops,
          risk_level: response.risk_level,
          request_class: response.request_class,
          objective_tag: response.objective_tag,
          audit: response.audit || null,
        },
        screenshots: {
          loaded: `screenshots/${promptDef.id}-loaded.png`,
          response: `screenshots/${promptDef.id}-response.png`,
        },
        traces: traces.slice(0, 20), // Cap to avoid huge files
        quality,
        assertions: {
          no_crash: noCrash,
          behavior_match: behaviorMatch,
          family_match: familyMatch,
          op_types_match: opTypesMatch,
        },
        duration_ms: durationMs,
        timestamp: new Date().toISOString(),
      };

      // Save response record
      fs.writeFileSync(
        path.join(RESULTS_DIR, `${promptDef.id}.json`),
        JSON.stringify(record, null, 2) + '\n'
      );

      // ── Assertions ──

      // Handle rate limiting gracefully
      if (outcome === 'error') {
        const errorText = await errorMessage.textContent().catch(() => '');
        if (/429|rate.limit|quota/i.test(errorText || '')) {
          test.skip(true, 'LLM rate-limited — transient 429');
          return;
        }
      }

      // Tier 1: No crash/timeout/500
      expect(noCrash, `Prompt crashed or timed out (outcome=${outcome})`).toBe(true);

      // Tier 2: Behavior match
      if (promptDef.expected_behavior === 'produces_ops') {
        expect(ops.length, `Expected ops but got ${ops.length}`).toBeGreaterThanOrEqual(1);
      }
      if (promptDef.must_not_produce_ops) {
        expect(ops.length, `Expected no ops but got ${ops.length}`).toBe(0);
      }
      if (promptDef.expected_behavior === 'answer_only' || promptDef.expected_behavior === 'report') {
        expect(
          (response.message?.length || 0) > 0,
          'Expected non-empty message for answer/report'
        ).toBe(true);
      }
    });
  }
});
