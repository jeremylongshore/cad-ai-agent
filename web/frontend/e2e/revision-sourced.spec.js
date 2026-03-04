// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

// Externally-sourced DXF files from open-source repos (see SOURCES.md)
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const SOURCED = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo', 'sourced');

// Comparison API can be slow on production (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;

// Pick specific sourced files for cross-document comparison tests.
// These pairs are chosen for variety: different formats, entity counts, and sources.
const REVISION_PAIRS = [
  { master: 'jscad-floorplan.dxf', revision: 'jscad-entities.dxf', label: 'floorplan vs entities' },
  { master: 'jscad-2Dlines.dxf', revision: 'jscad-2Dcircles.dxf', label: '2D lines vs circles' },
  { master: 'gds-api-cw750-details.dxf', revision: 'jscad-CustomBlocks.dxf', label: 'curtain wall vs custom blocks' },
  { master: 'assimp-PinkEggFromLW.dxf', revision: 'jscad-3d-entities.dxf', label: 'assimp egg vs bourke 3D' },
  { master: 'jscad-blocks1.dxf', revision: 'jscad-blocks2.dxf', label: 'blocks1 vs blocks2' },
];

test.describe('Revision Comparison — Sourced Documents', () => {
  // Guard: skip if sourced files don't exist
  const allExist = REVISION_PAIRS.every(
    p => fs.existsSync(path.join(SOURCED, p.master)) && fs.existsSync(path.join(SOURCED, p.revision))
  );
  test.skip(!allExist, 'Sourced DXF files missing — run scripts/download_sourced_fixtures.sh');

  for (const { master, revision, label } of REVISION_PAIRS) {
    test(`compare ${label} (${master} vs ${revision})`, async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

      // Upload master
      await page.locator('input[type="file"]').setInputFiles(path.join(SOURCED, master));
      await expect(
        page.locator('.message--system').filter({ hasText: 'Loaded' })
      ).toBeVisible({ timeout: 30_000 });

      // Switch to Compare tab
      const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
      await compareTab.click();
      await expect(compareTab).toHaveClass(/preview__tab--active/);

      // Upload revision
      const revisionInput = page.locator('input#revision-upload');
      await revisionInput.setInputFiles(path.join(SOURCED, revision));

      // Wait for comparison to complete — float bar, ops list, or compact step all signal done
      const comparisonReady = page.locator(
        '.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact'
      );
      await expect(comparisonReady.first()).toBeVisible({ timeout: COMPARE_TIMEOUT });

      // Different files → must detect changes
      const floatBar = page.locator('.compare-float-bar--bottom');
      const floatBarText = await floatBar.textContent();
      expect(floatBarText).not.toContain('No changes detected');

      // At least one diff badge should be present inside the float bar
      const badges = floatBar.locator('.comparison-badge');
      const badgeCount = await badges.count();
      expect(badgeCount).toBeGreaterThanOrEqual(1);

      console.log(`[ok] ${label} — ${floatBarText?.slice(0, 120)}`);
    });
  }
});
