import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  timeout: 90_000,
  use: { baseURL: 'http://127.0.0.1:4177', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: process.env.PLAYWRIGHT_CHANNEL as 'chrome' | undefined } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: [{
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4177 --strictPort`,
    url: 'http://127.0.0.1:4177/tests/fixtures/upload.html',
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: 'http://127.0.0.1:4177/test-api',
      VITE_SUPABASE_URL: 'http://127.0.0.1:4177/test-storage', VITE_SUPABASE_ANON_KEY: 'test-anon-key' },
  }, {
    command: `"${process.execPath}" tests/mockStorageServer.mjs`,
    url: 'http://127.0.0.1:4178/health',
    reuseExistingServer: false,
  }],
});
