import { defineConfig } from "@playwright/test"

/**
 * Browser smoke for the public demo console (tests/e2e/dashboard-demo.spec.ts).
 *
 * Boots `server.demo_app`, which needs no database, no tokens and no environment — that is
 * precisely why the demo can be exercised in CI at all.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:8020",
    headless: true,
    trace: "off",
  },
  webServer: {
    command:
      "python3 -m uvicorn server.demo_app:app --host 127.0.0.1 --port 8020",
    url: "http://127.0.0.1:8020/healthz",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: { PYTHONPATH: "service" },
  },
})
