import { defineConfig } from "@playwright/test"

// The spec starts (and stops) both the app and the stub host itself, so there is no
// `webServer` here: the tests need a handle on the stub to read what it received.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // one app process, one mutable bug flag — serial is the honest mode
  workers: 1,
  reporter: process.env.CI ? "line" : "list",
  timeout: 30_000,
  use: {
    headless: true,
    trace: "off",
  },
})
