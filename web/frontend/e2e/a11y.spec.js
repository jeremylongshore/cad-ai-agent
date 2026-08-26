// @a11y — axe-core-driven accessibility baseline.
// Runs against the dev server's primary surfaces. WCAG 2.1 AA target.
//
// AEC professionals using assistive tech (screen readers, keyboard-only,
// high-contrast modes) are a real persona — see PERSONAS.md "Reviewer /
// Compliance Officer" archetype. Violations break that persona's workflow.

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const SURFACES = [
  { name: 'Landing', path: '/' },
  { name: 'Login', path: '/login' },
];

for (const surface of SURFACES) {
  test(`@a11y ${surface.name} has no detectable WCAG 2.1 AA violations`, async ({ page }) => {
    await page.goto(surface.path);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // Disclose violations clearly so engineers can act on them
    if (results.violations.length > 0) {
      console.log(JSON.stringify(results.violations, null, 2));
    }
    expect(results.violations).toEqual([]);
  });
}
