// @ts-check
const { defineConfig } = require('@playwright/test');

const PORT = 8000;
const PYTHON =
  process.env.PYTHON || (process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python');

module.exports = defineConfig({
  testDir: './tests/playwright',
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
  },
  // Playwright starts the service before the tests and stops it afterwards.
  webServer: {
    command: `${PYTHON} -m uvicorn service.app:app --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
