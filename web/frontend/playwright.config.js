// @ts-check
import { defineConfig } from '@playwright/test';
import path from 'path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');

// TARGET=production tests the real deployed app
// TARGET=local (default) tests against local dev servers
const TARGET = process.env.TARGET || 'local';
const isProduction = TARGET === 'production';

const PROD_URL = 'https://cad-dxf-agent.web.app';
const LOCAL_URL = 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: 1,
  timeout: 90_000, // production can be slower (Cloud Run cold start)

  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],

  use: {
    baseURL: isProduction ? PROD_URL : LOCAL_URL,
    trace: 'on',
    screenshot: 'on',
    video: 'retain-on-failure',
    ...(process.env.PWDEBUG ? { launchOptions: { slowMo: 300 } } : {}),
  },

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  outputDir: './test-results',

  // Only start local servers when not testing production
  ...(isProduction ? {} : {
    webServer: [
      {
        command: [
          'CAD_WEB_DEV_MODE=1',
          'OTEL_ENABLED=1',
          'OTEL_EXPORTER=console',
          'CAD_LLM_PROVIDER=mock',
          `${PROJECT_ROOT}/.venv/bin/python -m uvicorn web.backend.main:app --port 8322`,
        ].join(' '),
        port: 8322,
        cwd: PROJECT_ROOT,
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
        stdout: 'pipe',
        stderr: 'pipe',
      },
      {
        command: 'npm run dev',
        port: 3000,
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
    ],
  }),
});
