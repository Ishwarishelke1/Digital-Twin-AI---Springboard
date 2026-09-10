// tests_e2e/page-walk.spec.js — docs/TEST_PLAN.md Phase 2.2.
//
// Every page, reached by DIRECT URL — never by clicking through. Sign-up was
// unreachable by direct navigation for months precisely because every manual
// test before this one arrived by clicking a link from the login page, which
// never remounts the auth context. goto() is the only way this class of bug
// gets caught.
import { test, expect } from "./fixtures.js";

// { path, landmark } — landmark is what proves the actual page rendered, not
// just that navigation resolved (an ErrorBoundary recovery screen is still a
// 200 with a title). Protected pages assert their real heading; public pages
// assert their own distinguishing text.
const PAGES = [
  { path: "/dashboard", landmark: "Dashboard" },
  { path: "/finance", landmark: "Finance Dashboard" },
  { path: "/study", landmark: "Study Dashboard" },
  { path: "/habits", landmark: "Habit Dashboard" },
  { path: "/goals", landmark: "Goals" },
  { path: "/prediction", landmark: "AI Prediction Dashboard" },
  { path: "/assistant", landmark: "Digital Twin AI Assistant" },
  { path: "/activity", landmark: "Activity History" },
  { path: "/profile", landmark: "My Digital Twin Profile" },
  { path: "/settings", landmark: "Settings" },
];

// Public pages: reachable with no session at all, so exercised through a
// separate, unauthenticated context rather than the seeded user's session —
// this is the actual regression class (sign-up unreachable when logged out).
const PUBLIC_PAGES = [
  { path: "/login", landmark: "Welcome Back" },
  { path: "/signup", landmark: "Create Account" },
  { path: "/forgot-password", landmark: "Forgot Password" },
];

test.describe("protected pages render with real data, no console/network noise", () => {
  for (const { path, landmark } of PAGES) {
    test(`${path} — direct URL renders "${landmark}"`, async ({ page, setTheme }, testInfo) => {
      await setTheme(testInfo.project.name === "dark");
      await page.goto(path);
      await expect(page.getByText(landmark, { exact: false }).first()).toBeVisible({ timeout: 10_000 });
    });
  }
});

test.describe("public pages", () => {
  test.use({ storageState: { cookies: [], origins: [] } }); // no session at all

  for (const { path, landmark } of PUBLIC_PAGES) {
    test(`${path} — direct URL, no session, renders "${landmark}"`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByText(landmark, { exact: false }).first()).toBeVisible({ timeout: 10_000 });
    });
  }
});

test("logout redirects a protected page to /login", async ({ browser }) => {
  // A throwaway, freshly REGISTERED account — not the shared seeded demo
  // login. token_version lives on the User document, not the cookie: bumping
  // it via logout invalidates every session for that account, not just the
  // one that called logout. Using the shared demo account here would silently
  // poison the storageState every other test (and the whole "dark" project,
  // which reuses the same file) depends on — confirmed the hard way, as all
  // ten "dark" protected-page tests failing with setTheme 401 the first time
  // this test ran against the shared account.
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const email = `pw-logout-${Date.now()}@example.com`;

  await page.goto("/signup");
  await page.getByPlaceholder(/enter.*name/i).fill("Logout Test");
  await page.getByPlaceholder(/enter.*email/i).fill(email);
  await page.getByPlaceholder(/enter.*password/i).fill("a-genuinely-fine-password-1");
  await page.getByPlaceholder(/confirm.*password/i).fill("a-genuinely-fine-password-1");
  await page.getByPlaceholder(/age/i).fill("25");
  await page.getByRole("button", { name: /sign ?up|create account/i }).click();
  await expect(page.getByText("Dashboard", { exact: false }).first()).toBeVisible({ timeout: 10_000 });

  await page.evaluate(async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
  });
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await ctx.close();
});
