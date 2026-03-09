// @ts-check
/**
 * Global setup: sign in anonymously once and save the auth state.
 * All tests reuse this storage state, avoiding repeated signInAnonymously
 * calls that trigger Firebase rate limiting.
 */
import { chromium } from '@playwright/test';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const STORAGE_STATE_PATH = path.join(import.meta.dirname, '..', 'test-results', '.auth-state.json');

export default async function globalSetup(config) {
  const projectRoot = path.resolve(import.meta.dirname, '..', '..', '..');

  // Download sourced DXF fixtures if not already present (idempotent)
  const sourcedScript = path.join(projectRoot, 'scripts', 'download_sourced_fixtures.sh');
  const e2eScript = path.join(projectRoot, 'scripts', 'download_e2e_fixtures.sh');

  for (const script of [sourcedScript, e2eScript]) {
    if (fs.existsSync(script)) {
      try {
        execSync(`bash "${script}"`, { cwd: projectRoot, timeout: 120_000, stdio: 'pipe' });
      } catch (e) {
        console.warn(`Fixture download script failed (non-fatal): ${e.message}`);
      }
    }
  }

  const baseURL = config.projects[0].use.baseURL || 'http://localhost:3000';

  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto(baseURL);
  // Wait for Firebase anonymous auth to complete — h2 appears when auth is done
  await page.locator('h2').waitFor({ state: 'visible', timeout: 30_000 });

  // Save auth state (includes Firebase IndexedDB tokens)
  await page.context().storageState({ path: STORAGE_STATE_PATH });

  await browser.close();
}

export { STORAGE_STATE_PATH };
