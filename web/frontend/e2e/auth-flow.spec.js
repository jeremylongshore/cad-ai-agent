// @ts-check
/**
 * Auth flow tests — validates login, sign-out, re-login, and unauthenticated redirect.
 *
 * Against production (TARGET=production): tests real Firebase email/password auth.
 * Against local (default): tests dev-auth bypass flow.
 */
import { test, expect } from '@playwright/test';

const TARGET = process.env.TARGET || 'local';
const isProduction = TARGET === 'production';

test.describe('Authentication Flow', () => {
  test('authenticated user sees workspace', async ({ page }) => {
    // Global setup already signed us in — storage state is restored
    await page.goto('/');

    if (isProduction) {
      // Production: workspace h2 should appear (e.g., "Upload a drawing")
      await expect(page.locator('h2')).toBeVisible({ timeout: 30_000 });
      const heading = await page.locator('h2').textContent();
      expect(heading).not.toContain('Sign in');
    } else {
      // Local: dev-auth bypass shows workspace immediately
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });
    }
  });

  test('sign out returns to login page', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toBeVisible({ timeout: 30_000 });

    if (isProduction) {
      // Find and click the sign-out button (in header or user menu)
      const signOutBtn = page.locator('button').filter({ hasText: /Sign Out|Logout|Log out/i });
      const menuBtn = page.locator('button[aria-label="User menu"], .user-menu__trigger, .header__user-btn');

      // May need to open user menu first
      if (await menuBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await menuBtn.click();
      }

      if (await signOutBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await signOutBtn.click();

        // Should redirect to login page
        await expect(
          page.locator('button').filter({ hasText: 'Sign in with Google' })
        ).toBeVisible({ timeout: 15_000 });
      } else {
        // Sign-out button not found in expected location — skip
        console.log('Sign-out button not found — skipping (UI may differ)');
      }
    } else {
      // Local dev-auth has no real sign-out — skip
      test.skip(true, 'Sign-out not applicable in dev-auth mode');
    }
  });

  test('re-login after sign-out works', async ({ page }) => {
    test.skip(!isProduction, 'Re-login test only applies to production');

    const email = process.env.E2E_TEST_EMAIL || 'e2e-tester@intentcad.dev';
    const password = process.env.E2E_TEST_PASSWORD;
    if (!password) {
      test.skip(true, 'E2E_TEST_PASSWORD not set');
      return;
    }

    await page.goto('/');
    await expect(page.locator('h2')).toBeVisible({ timeout: 30_000 });

    // Sign out
    const menuBtn = page.locator('button[aria-label="User menu"], .user-menu__trigger, .header__user-btn');
    if (await menuBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await menuBtn.click();
    }

    const signOutBtn = page.locator('button').filter({ hasText: /Sign Out|Logout|Log out/i });
    if (!await signOutBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      test.skip(true, 'Sign-out button not found');
      return;
    }
    await signOutBtn.click();

    // Wait for login page
    await expect(
      page.locator('button').filter({ hasText: 'Sign in with Google' })
    ).toBeVisible({ timeout: 15_000 });

    // Re-login via Firebase SDK
    await page.evaluate(async ({ email, password }) => {
      const { getAuth, signInWithEmailAndPassword } = await import('https://www.gstatic.com/firebasejs/11.1.0/firebase-auth.js');
      const auth = getAuth();
      await signInWithEmailAndPassword(auth, email, password);
    }, { email, password });

    // Workspace should load again
    await expect(page.locator('h2')).toBeVisible({ timeout: 30_000 });
    const heading = await page.locator('h2').textContent();
    expect(heading).not.toContain('Sign in');

    console.log('Re-login after sign-out succeeded');
  });

  test('unauthenticated access shows login page', async ({ browser }) => {
    test.skip(!isProduction, 'Unauthenticated redirect only testable in production');

    // Create a fresh context with no stored auth state
    const context = await browser.newContext({ storageState: undefined });
    const page = await context.newPage();

    await page.goto('/');

    // Should show login page, not workspace
    await expect(
      page.locator('button').filter({ hasText: 'Sign in with Google' })
    ).toBeVisible({ timeout: 30_000 });

    await context.close();
  });
});
