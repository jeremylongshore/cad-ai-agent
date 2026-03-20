// @ts-check
/**
 * Global setup: authenticate once and save the auth state.
 *
 * - LOCAL mode (default): uses dev-auth bypass (VITE_DEV_AUTH=1)
 * - PRODUCTION mode (TARGET=production): signs in via email/password
 *   using the E2E test account (e2e-tester@intentcad.dev).
 *
 * All tests reuse the saved storage state to avoid repeated auth calls.
 */
import { chromium } from '@playwright/test';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const STORAGE_STATE_PATH = path.join(import.meta.dirname, '..', 'test-results', '.auth-state.json');

const TARGET = process.env.TARGET || 'local';
const isProduction = TARGET === 'production';

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

  // Ensure test-results directory exists for storage state
  fs.mkdirSync(path.dirname(STORAGE_STATE_PATH), { recursive: true });

  const baseURL = config.projects[0].use.baseURL || 'http://localhost:3000';

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  if (isProduction) {
    // --- Production auth: email/password via Firebase SDK ---
    const email = process.env.E2E_TEST_EMAIL || 'e2e-tester@intentcad.dev';
    const password = process.env.E2E_TEST_PASSWORD;
    if (!password) {
      await browser.close();
      throw new Error(
        'E2E_TEST_PASSWORD env var required for production tests. ' +
        'Set it in .env.test or pass via environment.'
      );
    }

    await page.goto(baseURL);

    // Wait for the login page to be ready (Firebase SDK loaded)
    await page.locator('button').filter({ hasText: 'Sign in with Google' }).waitFor({
      state: 'visible',
      timeout: 30_000,
    });

    // Sign in via Firebase SDK directly in the browser context
    await page.evaluate(async ({ email, password }) => {
      const { initializeApp } = await import('https://www.gstatic.com/firebasejs/11.1.0/firebase-app.js');
      const { getAuth, signInWithEmailAndPassword } = await import('https://www.gstatic.com/firebasejs/11.1.0/firebase-auth.js');

      // Use the same config as the app (read from window or hardcode project config)
      const config = {
        apiKey: 'AIzaSyD2ocFCZ9h9xZqU0GYojASqpsA1IwIIpGI',
        authDomain: 'cad-dxf-agent.firebaseapp.com',
        projectId: 'cad-dxf-agent',
      };

      // Firebase may already be initialized — try getAuth on existing app
      let auth;
      try {
        const app = initializeApp(config, '__e2e_auth__');
        auth = getAuth(app);
      } catch {
        auth = getAuth();
      }

      await signInWithEmailAndPassword(auth, email, password);
    }, { email, password });

    // Wait for the app to recognize the auth state and show workspace
    await page.locator('h2').waitFor({ state: 'visible', timeout: 30_000 });

    console.log(`Production auth: signed in as ${email}`);
  } else {
    // --- Local auth: dev-mode bypass (VITE_DEV_AUTH=1) ---
    await page.goto(baseURL);
    // Wait for Firebase anonymous auth to complete — h2 appears when auth is done
    await page.locator('h2').waitFor({ state: 'visible', timeout: 30_000 });
  }

  // Save auth state (includes Firebase IndexedDB tokens)
  await page.context().storageState({ path: STORAGE_STATE_PATH });

  await browser.close();
}

export { STORAGE_STATE_PATH };
