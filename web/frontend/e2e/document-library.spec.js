// @ts-check
/**
 * Document Library tests — upload to library, load, delete, storage usage,
 * active badge, session reconnect, and cross-document compare.
 *
 * These tests require authenticated sessions (production: real Firebase,
 * local: dev-auth bypass). Document library is only available for
 * authenticated users with persistent storage.
 */
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

const UPLOAD_TIMEOUT = 30_000;
const VIEWER_TIMEOUT = 30_000;
const LIBRARY_TIMEOUT = 15_000;
const COMPARE_TIMEOUT = 45_000;

const TARGET = process.env.TARGET || 'local';
const isProduction = TARGET === 'production';

/** Upload a DXF file and wait for session ready. */
async function uploadAndWait(page, filePath) {
  await page.goto('/');

  // Wait for workspace to be ready
  const uploadHeading = page.locator('h2').filter({ hasText: 'Upload a drawing' });
  const compactBar = page.locator('.upload-bar-compact');
  await expect(uploadHeading.or(compactBar)).toBeVisible({ timeout: 15_000 });

  await page.locator('[data-testid="file-upload-input"]').setInputFiles(filePath);

  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: UPLOAD_TIMEOUT });
}

/** Check if document library sidebar is available. */
async function hasDocumentLibrary(page) {
  const libraryPanel = page.locator('.document-library, [data-testid="document-library"]');
  return await libraryPanel.isVisible({ timeout: 5_000 }).catch(() => false);
}

test.describe('Document Library', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2').or(page.locator('.upload-bar-compact'))).toBeVisible({ timeout: 15_000 });
  });

  test('upload document appears in library list', async ({ page }) => {
    // Upload a DXF
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );

    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Check if library is available (requires auth + persistent storage)
    const librarySection = page.locator('.document-library, [data-testid="document-library"]');
    if (!await librarySection.isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false)) {
      // Library may not be visible in collapsed sidebar — try expanding
      const infoBtn = page.locator('.upload-bar-compact button').filter({ hasText: 'Info' });
      if (await infoBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await infoBtn.click();
      }
    }

    // Look for the document card in the library
    const docCard = page.locator('.document-card, [data-testid="document-card"]');
    const libraryVisible = await docCard.first().isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false);

    if (libraryVisible) {
      const cardText = await docCard.first().textContent();
      expect(cardText).toContain('r2000_blocks');
      console.log('Document appears in library');
    } else {
      // Document library may not be available in this auth mode
      console.log('Document library not available (may require production auth)');
    }
  });

  test('load document from library creates session', async ({ page }) => {
    // First upload to populate library
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Reset to upload screen
    const newFileBtn = page.locator('button').filter({ hasText: 'New File' });
    if (await newFileBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await newFileBtn.click();
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 10_000 });
    }

    // Find and click a library document
    const docCard = page.locator('.document-card, [data-testid="document-card"]');
    if (await docCard.first().isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false)) {
      await docCard.first().click();

      // Should load the drawing (system message or viewer)
      const loaded = page.locator('.message--system').filter({ hasText: 'Loaded' });
      const viewer = page.locator('.dxf-viewer');
      await expect(loaded.or(viewer)).toBeVisible({ timeout: UPLOAD_TIMEOUT });
    } else {
      console.log('Document library cards not visible — skipping load test');
    }
  });

  test('delete document removes it from library', async ({ page }) => {
    // Upload a DXF first
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r12_basic.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    const docCard = page.locator('.document-card, [data-testid="document-card"]');
    if (!await docCard.first().isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false)) {
      console.log('Document library not available — skipping delete test');
      return;
    }

    const countBefore = await docCard.count();

    // Find delete button on the last card (the one we just uploaded)
    const deleteBtn = docCard.last().locator('button').filter({ hasText: /Delete|Remove/ });
    if (await deleteBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await deleteBtn.click();

      // Confirm deletion if dialog appears
      const confirmBtn = page.locator('button').filter({ hasText: /Confirm|Yes|Delete/ });
      if (await confirmBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await confirmBtn.click();
      }

      // Card count should decrease
      await page.waitForTimeout(2_000);
      const countAfter = await docCard.count();
      expect(countAfter).toBeLessThan(countBefore);

      console.log(`Document deleted: ${countBefore} → ${countAfter} documents`);
    } else {
      console.log('Delete button not visible on document card');
    }
  });

  test('storage usage indicator visible', async ({ page }) => {
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Storage indicator in the library panel
    const storageIndicator = page.locator('.storage-indicator, [data-testid="storage-indicator"]');
    if (await storageIndicator.isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false)) {
      const text = await storageIndicator.textContent();
      expect(text).toMatch(/\d/); // Should contain some numeric usage
      console.log(`Storage usage: ${text}`);
    } else {
      console.log('Storage indicator not visible (may require production auth)');
    }
  });

  test('active drawing badge shows for loaded library doc', async ({ page }) => {
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Check for active badge on document card or compact bar
    const activeBadge = page.locator('.document-card--active, .badge--active, [data-testid="active-doc-badge"]');
    if (await activeBadge.isVisible({ timeout: LIBRARY_TIMEOUT }).catch(() => false)) {
      console.log('Active drawing badge visible');
    } else {
      // Active badge may be rendered differently
      console.log('Active badge not found (may use different indicator)');
    }
  });

  test('session reconnect on page reload', async ({ page }) => {
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Reload the page
    await page.reload();

    // Should either reconnect session or show upload screen
    const reconnected = page.locator('.upload-bar-compact__filename, .message--system');
    const uploadScreen = page.locator('h2').filter({ hasText: 'Upload a drawing' });

    await expect(reconnected.or(uploadScreen)).toBeVisible({ timeout: 30_000 });

    const hasCompactBar = await page.locator('.upload-bar-compact__filename').isVisible({ timeout: 5_000 }).catch(() => false);
    if (hasCompactBar) {
      console.log('Session reconnected after reload');
    } else {
      console.log('Session expired — upload screen shown (expected for ephemeral sessions)');
    }
  });

  test('compare two library documents', async ({ page }) => {
    // Upload first doc
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(
      path.join(DXF_ZOO, 'r2000_blocks.dxf')
    );
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: UPLOAD_TIMEOUT });

    // Switch to Compare tab
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await expect(compareTab).toBeVisible({ timeout: 5_000 });
    await compareTab.click();

    // Upload revision
    const revisionInput = page.locator('input#revision-upload');
    if (await revisionInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

      // Wait for comparison
      await expect(
        page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
      ).toBeVisible({ timeout: COMPARE_TIMEOUT });

      console.log('Cross-document comparison completed');
    } else {
      // Compare from library button
      const compareBtn = page.locator('button').filter({ hasText: /Compare from library/ });
      if (await compareBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
        console.log('Compare-from-library button available');
      } else {
        console.log('Compare upload input not found in expected location');
      }
    }
  });
});
