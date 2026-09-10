// playwright.config.js — docs/TEST_PLAN.md Phase 2. Drives the app through a
// real browser exactly as a user would — the layer 0 unit tests and 0
// integration tests left uncovered. See tests_e2e/README.md for how to run
// this and what it assumes is already running.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests_e2e",
  fullyParallel: false, // shared storageState/backend — avoid cross-test races
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "tests_e2e/report" }]],

  // Vite's dev server already proxies /api to 127.0.0.1:8000 (vite.config.js)
  // so navigating within this baseURL is same-origin — the httpOnly auth
  // cookie behaves exactly as it does for a real user, no special test-only
  // auth path.
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 30_000,
  },

  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.CHROME_EXE
      ? { executablePath: process.env.CHROME_EXE }
      : undefined,
  },

  // Both projects share ONE storageState (same seeded account, same cookie) —
  // dark mode here is not a browser setting Playwright can emulate
  // (colorScheme does nothing; see tests_e2e/README.md for why) or a separate
  // account per theme; it's one field on the account's own preferences,
  // flipped server-side by a fixture (tests_e2e/fixtures.js) before each test
  // in the "dark" project runs, then reloaded.
  projects: [
    {
      name: "light",
      use: { ...devices["Desktop Chrome"], storageState: "tests_e2e/.auth/user.json" },
      testMatch: /.*\.spec\.js/,
    },
    {
      name: "dark",
      use: { ...devices["Desktop Chrome"], storageState: "tests_e2e/.auth/user.json" },
      testMatch: /.*\.spec\.js/,
    },
  ],

  globalSetup: "./tests_e2e/global-setup.js",
});
