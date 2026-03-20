// @ts-check
/**
 * Global setup: authenticate once and save the auth state.
 *
 * - LOCAL mode (default): uses dev-auth bypass (VITE_DEV_AUTH=1)
 * - PRODUCTION mode (TARGET=production): signs in via Firebase Auth REST API
 *   then uses Playwright's route interception to inject auth tokens into
 *   backend API calls. The app's useAuth hook picks up the auth state.
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

const FIREBASE_API_KEY = 'AIzaSyD2ocFCZ9h9xZqU0GYojASqpsA1IwIIpGI';

/**
 * Sign in via Firebase Auth REST API (no SDK needed).
 */
async function firebaseSignIn(email, password) {
  const resp = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
    }
  );
  const data = await resp.json();
  if (data.error) {
    throw new Error(`Firebase sign-in failed: ${data.error.message}`);
  }
  return data;
}

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
    // --- Production auth: sign in via REST API, inject via script tag ---
    const email = process.env.E2E_TEST_EMAIL || 'e2e-tester@intentcad.dev';
    const password = process.env.E2E_TEST_PASSWORD;
    if (!password) {
      await browser.close();
      throw new Error(
        'E2E_TEST_PASSWORD env var required for production tests. ' +
        'Set it in .env.test or pass via environment.'
      );
    }

    // 1. Sign in via REST API (Node.js side)
    console.log(`Signing in as ${email} via Firebase REST API...`);
    const signInResult = await firebaseSignIn(email, password);

    // 2. Use addInitScript to inject auth state BEFORE Firebase initializes.
    //    This writes to IndexedDB synchronously (via a blocking pattern)
    //    before the app's Firebase SDK reads from it.
    const authPayload = JSON.stringify({
      apiKey: FIREBASE_API_KEY,
      uid: signInResult.localId,
      email: signInResult.email,
      refreshToken: signInResult.refreshToken,
      idToken: signInResult.idToken,
    });

    await context.addInitScript(`
      (function() {
        var payload = ${authPayload};
        var dbName = 'firebaseLocalStorageDb';
        var storeName = 'firebaseLocalStorage';
        var key = 'firebase:authUser:' + payload.apiKey + ':[DEFAULT]';

        var authUser = {
          uid: payload.uid,
          email: payload.email,
          emailVerified: false,
          displayName: null,
          isAnonymous: false,
          providerData: [{
            providerId: 'password',
            uid: payload.email,
            displayName: null,
            email: payload.email,
            phoneNumber: null,
            photoURL: null,
          }],
          stsTokenManager: {
            refreshToken: payload.refreshToken,
            accessToken: payload.idToken,
            expirationTime: Date.now() + 3600 * 1000,
          },
          createdAt: String(Date.now()),
          lastLoginAt: String(Date.now()),
          apiKey: payload.apiKey,
          appName: '[DEFAULT]',
        };

        // Open IndexedDB and write auth user — Firebase reads this on init
        var req = indexedDB.open(dbName);
        req.onupgradeneeded = function(e) {
          var db = e.target.result;
          if (!db.objectStoreNames.contains(storeName)) {
            db.createObjectStore(storeName);
          }
        };
        req.onsuccess = function(e) {
          var db = e.target.result;
          if (!db.objectStoreNames.contains(storeName)) {
            db.close();
            var req2 = indexedDB.open(dbName, db.version + 1);
            req2.onupgradeneeded = function(e2) {
              e2.target.result.createObjectStore(storeName);
            };
            req2.onsuccess = function(e2) {
              var db2 = e2.target.result;
              var tx = db2.transaction(storeName, 'readwrite');
              tx.objectStore(storeName).put({ fbase_key: key, value: authUser }, key);
              tx.oncomplete = function() { db2.close(); };
            };
          } else {
            var tx = db.transaction(storeName, 'readwrite');
            tx.objectStore(storeName).put({ fbase_key: key, value: authUser }, key);
            tx.oncomplete = function() { db.close(); };
          }
        };
      })();
    `);

    // 3. Navigate to the app — Firebase SDK will find auth user in IndexedDB
    await page.goto(baseURL);

    // 4. Wait for workspace to load (proves auth state was picked up)
    await page.locator('h2').waitFor({ state: 'visible', timeout: 30_000 });

    const heading = await page.locator('h2').textContent();
    console.log(`Production auth: signed in as ${email}, page shows: "${heading}"`);
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
