import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 3100);
const frontendBaseURL = `http://127.0.0.1:${frontendPort}`;
const localhostBaseURL = `http://localhost:${frontendPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: frontendBaseURL,
    trace: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer: [
    {
      command: "cd .. && python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000",
      url: "http://127.0.0.1:5000/health",
      env: {
        FRONTEND_ORIGIN: frontendBaseURL,
        FRONTEND_ORIGINS: `${frontendBaseURL},${localhostBaseURL}`
      },
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      command: `npm run start -- --hostname 127.0.0.1 --port ${frontendPort}`,
      url: `${frontendBaseURL}/login`,
      reuseExistingServer: true,
      timeout: 120_000
    }
  ]
});
