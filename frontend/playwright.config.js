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
    // --disable-background-networking stops Chrome's own telemetry/GCM
    // registration calls, which otherwise retry for a while against a
    // restricted network and slow browser launch — harmless to keep even
    // where it isn't needed.
    launchOptions: process.env.CHROME_EXE
      ? { executablePath: process.env.CHROME_EXE, args: ["--disable-background-networking"] }
      : undefined,
  },

  // All projects share ONE storageState (same seeded account, same cookie) —
  // dark mode here is not a browser setting Playwright can emulate
  // (colorScheme does nothing; see tests_e2e/README.md for why) or a separate
  // account per theme; it's one field on the account's own preferences,
  // flipped server-side by a fixture (tests_e2e/fixtures.js) before each test
  // in a "dark"/"mobile-dark" project runs, then reloaded.
  //
  // mobile-light/mobile-dark add real phone-viewport coverage (390x844)
  // alongside the existing desktop light/dark pair — docs/TEST_PLAN.md's
  // "Still open" list named mobile as untested; nothing before this ran
  // under any viewport narrower than desktop.
  //
  // browserName: "chromium" is deliberate, not incidental: devices["iPhone 12"]
  // ships defaultBrowserType: "webkit" (real iOS only ever runs WebKit), which
  // this project's toolchain has never installed — only Chromium is set up
  // here (see tests_e2e/README.md's CHROME_EXE fallback). Spreading the device
  // preset without this override sends every mobile project to a WebKit binary
  // that doesn't exist, either failing instantly ("Executable doesn't exist")
  // or, worse, hanging until launch-timeout if an unrelated executablePath
  // happens to be set — both were hit and misdiagnosed as sandbox flakiness
  // before this line was traced down as the actual cause. This keeps the same
  // engine (Chromium) the rest of the suite already uses, just at a phone
  // viewport/UA/touch profile — real Mobile Safari (WebKit) coverage is a
  // separate, not-yet-done addition, not what this pair claims to test.
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
    {
      name: "mobile-light",
      use: { ...devices["iPhone 12"], browserName: "chromium", storageState: "tests_e2e/.auth/user.json" },
      testMatch: /.*\.spec\.js/,
    },
    {
      name: "mobile-dark",
      use: { ...devices["iPhone 12"], browserName: "chromium", storageState: "tests_e2e/.auth/user.json" },
      testMatch: /.*\.spec\.js/,
    },
  ],

  globalSetup: "./tests_e2e/global-setup.js",
});
