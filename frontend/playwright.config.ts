import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:8000', browserName: 'chromium', channel: 'msedge', headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  reporter: [['list'], ['json', { outputFile: '../artifacts/e2e-results.json' }]],
  webServer: { command: '.runtime\\python\\python.exe -m uvicorn firetrust.api:app --host 127.0.0.1 --port 8000', cwd: '..', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: true, timeout: 30000 }
})
