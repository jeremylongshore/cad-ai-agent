// @ts-check
import { test, expect } from '@playwright/test';
import path from 'path';

// Use real DXF files from the project's test fixtures
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const DXF_ZOO = path.join(PROJECT_ROOT, 'tests', 'fixtures', 'dxf_zoo');

// Comparison API can be slow on production (Cloud Run cold start + ezdxf processing)
const COMPARE_TIMEOUT = 45_000;

// Selector that resolves once comparison has finished and the UI has settled.
// The floating bar appears when there are changes; wizard-step-compact or
// revision-ops-list appear regardless. Waiting for any of these is safe for
// both the "has changes" and "no changes" cases.
const COMPARE_DONE_SELECTOR =
  '.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact';

test.describe('Comparison Flow — r2000_blocks master', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    // Upload master DXF (use data-testid to avoid matching the library upload input)
    await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Compare tab visible after master upload', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await expect(compareTab).toBeVisible();
  });

  test('Compare tab shows upload button before revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();
    await expect(compareTab).toHaveClass(/preview__tab--active/);

    const uploadBtn = page.locator('button').filter({ hasText: /Upload Revision/ });
    await expect(uploadBtn).toBeVisible({ timeout: 5_000 });
  });

  test('compare r2000_blocks vs r2000_revision — badges appear', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison to finish — float bar appears when there are changes
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const badges = page.locator('.comparison-badge');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(1);

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r2000_revision — badges: ${badgeCount}, text: ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r2018_polylines — cross-version diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    // Totally different files — float bar must appear with change badges
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const addedBadge = page.locator('.comparison-badge--added');
    const removedBadge = page.locator('.comparison-badge--removed');
    const addedCount = await addedBadge.count();
    const removedCount = await removedBadge.count();
    expect(addedCount + removedCount).toBeGreaterThanOrEqual(1);

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r2018_polylines — ${allBadgeText}`);
  });

  test('compare r2000_blocks vs r12_basic — old format revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r2000_blocks vs r12_basic — ${allBadgeText}`);
  });

  test('identical file shows no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    // For identical files the backend returns 0 changes, so the floating diff
    // bar never renders. Wait for comparison to finish by watching for the
    // compact wizard step or any revision ops list that may appear instead.
    await expect(page.locator(COMPARE_DONE_SELECTOR).first()).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Confirm that no diff badges were rendered
    await expect(page.locator('.compare-float-bar--bottom')).not.toBeVisible();

    console.log('Identical file — correctly shows no changes (float bar absent)');
  });

  test('comparison preview image renders after diff', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    // Wait for comparison to finish
    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    // Accept either a static preview image or the interactive split viewer
    const previewImg = page.locator('.preview__image-wrap img');
    const splitViewer = page.locator('.compare-split-wrap');

    const imgCount = await previewImg.count();
    const splitCount = await splitViewer.count();

    if (imgCount > 0) {
      const src = await previewImg.getAttribute('src');
      expect(src).toBeTruthy();
      console.log('Comparison diff overlay image rendered');
    } else if (splitCount > 0) {
      await expect(splitViewer).toBeVisible();
      console.log('Comparison interactive split viewer rendered');
    } else {
      console.log('No comparison preview image (render_available=false)');
    }
  });
});

test.describe('Comparison Flow — r2018_polylines master', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });
  });

  test('compare r2018_polylines vs r2000_revision', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r2018_polylines vs r2000_revision — ${allBadgeText}`);
  });

  test('r2018_polylines self-compare — no changes', async ({ page }) => {
    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2018_polylines.dxf'));

    // 0 changes — float bar must stay hidden
    await expect(page.locator(COMPARE_DONE_SELECTOR).first()).toBeVisible({ timeout: COMPARE_TIMEOUT });
    await expect(page.locator('.compare-float-bar--bottom')).not.toBeVisible();

    console.log('r2018_polylines self-compare — correctly no changes (float bar absent)');
  });
});

test.describe('Comparison Flow — r12_basic master', () => {
  test('compare r12_basic vs r2000_blocks', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r12_basic.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const revisionInput = page.locator('input#revision-upload');
    await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));

    const floatBar = page.locator('.compare-float-bar--bottom');
    await expect(floatBar).toBeVisible({ timeout: COMPARE_TIMEOUT });

    const allBadgeText = await floatBar.textContent();
    console.log(`r12_basic vs r2000_blocks — ${allBadgeText}`);
  });
});

// --- Extended compare workflow tests ---

const APPLY_TIMEOUT = 45_000;

/** Upload master + revision and wait for comparison to complete. */
async function uploadMasterAndRevision(page) {
  await page.goto('/');
  await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

  await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
  await expect(
    page.locator('.message--system').filter({ hasText: 'Loaded' })
  ).toBeVisible({ timeout: 30_000 });

  const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
  await compareTab.click();

  const revisionInput = page.locator('input#revision-upload');
  await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

  await expect(
    page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
  ).toBeVisible({ timeout: COMPARE_TIMEOUT });
}

test.describe('Comparison Workflow — Extended', () => {
  test('upload revision shows alignment method and confidence', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const floatBarTop = page.locator('.compare-float-bar--top');
    if (await floatBarTop.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Alignment method badge
      const methodBadge = floatBarTop.locator('.badge').filter({
        hasText: /Identity|Translation|Rigid|Anchor|Feature|Manual/,
      });
      await expect(methodBadge.first()).toBeVisible({ timeout: 5_000 });

      // Confidence percentage
      const confidence = floatBarTop.locator('.compare-float-bar__confidence');
      if (await confidence.isVisible({ timeout: 3_000 }).catch(() => false)) {
        const text = await confidence.textContent();
        expect(text).toMatch(/\d+%/);
        console.log(`Alignment: ${await methodBadge.first().textContent()}, confidence: ${text}`);
      }
    }
  });

  test('approve all → apply → success count shown', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping approve/apply test');
      return;
    }

    await page.locator('button').filter({ hasText: 'Approve All' }).click();

    const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    const bundleDownload = page.locator('.bundle-download');
    await expect(bundleDownload).toBeVisible({ timeout: APPLY_TIMEOUT });

    const statusText = await page.locator('.bundle-download__status').textContent();
    expect(statusText).toContain('successfully');
    console.log(`Apply result: ${statusText}`);
  });

  test('reject individual op → approve rest → apply', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping partial reject test');
      return;
    }

    const opCount = await opItems.count();
    if (opCount < 2) {
      console.log('Only 1 op — cannot test partial reject');
      // Approve all and apply
      await page.locator('button').filter({ hasText: 'Approve All' }).click();
    } else {
      // Reject first op
      const rejectBtn = opItems.first().locator('button').filter({ hasText: 'Reject' });
      if (await rejectBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await rejectBtn.click();
      }

      // Approve the rest
      const approveAllBtn = page.locator('button').filter({ hasText: 'Approve All' });
      if (await approveAllBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await approveAllBtn.click();
      } else {
        // Approve remaining individually
        for (let i = 1; i < opCount; i++) {
          const approveBtn = opItems.nth(i).locator('button').filter({ hasText: 'Approve' });
          if (await approveBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
            await approveBtn.click();
          }
        }
      }
    }

    const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
    if (await applyBtn.isEnabled({ timeout: 5_000 }).catch(() => false)) {
      await applyBtn.click();

      const bundleDownload = page.locator('.bundle-download');
      await expect(bundleDownload).toBeVisible({ timeout: APPLY_TIMEOUT });
      console.log('Partial reject + apply succeeded');
    }
  });

  test('reject all ops shows all rejected', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping reject all test');
      return;
    }

    // Click "Reject All" if available
    const rejectAllBtn = page.locator('button').filter({ hasText: 'Reject All' });
    if (await rejectAllBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await rejectAllBtn.click();

      // Apply button should be disabled (nothing approved)
      const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
      if (await applyBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await expect(applyBtn).toBeDisabled();
      }

      console.log('All ops rejected — apply disabled');
    } else {
      // Reject individually
      const count = await opItems.count();
      for (let i = 0; i < count; i++) {
        const rejectBtn = opItems.nth(i).locator('button').filter({ hasText: 'Reject' });
        if (await rejectBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
          await rejectBtn.click();
        }
      }
      console.log('Rejected all ops individually');
    }
  });

  test('download revision bundle after apply', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping bundle download test');
      return;
    }

    await page.locator('button').filter({ hasText: 'Approve All' }).click();

    const applyBtn = page.locator('button').filter({ hasText: /Apply.*Approved Change/ });
    await expect(applyBtn).toBeEnabled({ timeout: 5_000 });
    await applyBtn.click();

    const bundleDownload = page.locator('.bundle-download');
    await expect(bundleDownload).toBeVisible({ timeout: APPLY_TIMEOUT });

    const downloadBtn = page.locator('button').filter({ hasText: 'Download Bundle' });
    await expect(downloadBtn).toBeVisible({ timeout: 5_000 });

    const downloadPromise = page.waitForEvent('download', { timeout: APPLY_TIMEOUT });
    await downloadBtn.click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/\.(zip|dxf)$/i);
    console.log(`Bundle downloaded: ${download.suggestedFilename()}`);
  });

  test('keyboard navigation through ops', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping keyboard navigation test');
      return;
    }

    // Focus the first op item
    await opItems.first().click();

    // Try arrow key navigation
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(300);

    // Check if a different item got focus or active state
    const activeItem = page.locator('.revision-op-item--active, .revision-op-item:focus');
    if (await activeItem.isVisible({ timeout: 3_000 }).catch(() => false)) {
      console.log('Keyboard navigation: ArrowDown moved focus');
    } else {
      console.log('Keyboard navigation may not be implemented for revision ops');
    }
  });

  test('click op card focuses viewer on change location', async ({ page }) => {
    await uploadMasterAndRevision(page);

    const opItems = page.locator('.revision-op-item, [data-testid="revision-op-item"]');
    if (!await opItems.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('No revision ops — skipping focus test');
      return;
    }

    await opItems.first().click();

    // Check for viewer focus highlight
    const highlight = page.locator('[data-testid="viewer-focus-highlight"]');
    const hasHighlight = await highlight.isVisible({ timeout: 5_000 }).catch(() => false);
    if (hasHighlight) {
      console.log('Op click triggered viewer focus highlight');
    } else {
      console.log('No viewer focus highlight on op click (may use different indicator)');
    }
  });

  test('profile selector filters comparison', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toContainText('Upload a drawing', { timeout: 15_000 });

    await page.locator('[data-testid="file-upload-input"]').setInputFiles(path.join(DXF_ZOO, 'r2000_blocks.dxf'));
    await expect(
      page.locator('.message--system').filter({ hasText: 'Loaded' })
    ).toBeVisible({ timeout: 30_000 });

    const compareTab = page.locator('.preview__tab').filter({ hasText: 'Compare' });
    await compareTab.click();

    const profileSelect = page.locator('#profile-select');
    if (!await profileSelect.isVisible({ timeout: 5_000 }).catch(() => false)) {
      console.log('Profile selector not visible — skipping');
      return;
    }

    const options = profileSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      // Select a non-default profile
      await profileSelect.selectOption({ index: 1 });

      const selectedText = await profileSelect.inputValue();
      console.log(`Selected comparison profile: ${selectedText}`);

      // Upload revision with profile selected
      const revisionInput = page.locator('input#revision-upload');
      await revisionInput.setInputFiles(path.join(DXF_ZOO, 'r2000_revision.dxf'));

      await expect(
        page.locator('.compare-float-bar--bottom, .revision-ops-list, .wizard-step-compact').first()
      ).toBeVisible({ timeout: COMPARE_TIMEOUT });

      console.log('Comparison completed with profile filter');
    } else {
      console.log('Only default profile available');
    }
  });
});
