// tests_e2e/new-user.spec.js — a genuinely fresh account (registered in-test,
// never the seeded playwright-demo account), walking every protected page
// with zero data anywhere: no transactions, no study sessions, no habit logs,
// no goals. This is the band docs/TEST_PLAN.md's page walk never covered — it
// always ran against a data-rich seeded account.
//
// One test, not thirteen: /auth/register is rate-limited (core/rate_limit.py),
// so registering once and walking every page within that single session keeps
// this well under the limit instead of tripping it on a per-page test split.
import { test, expect } from "./fixtures.js";

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

// Tokens that would mean a raw JS/analytics artifact leaked into the UI
// instead of a proper empty state or formatted value — never legitimate
// visible copy in this app.
const FORBIDDEN_TOKENS = ["NaN", "Infinity", "undefined", "null"];

test.describe.configure({ mode: "serial" });

test.use({ storageState: { cookies: [], origins: [] } }); // no session — real signup below

test("brand-new user, zero data: every page renders cleanly, no fabricated figures", async ({ page }) => {
  const email = `pw-newuser-${Date.now()}@example.com`;

  await page.goto("/signup");
  await page.getByPlaceholder("Enter Full Name").fill("New User");
  await page.getByPlaceholder("Enter Email").fill(email);
  await page.getByPlaceholder("Enter Password").fill("a-genuinely-fine-password-1");
  await page.getByPlaceholder("Confirm Password").fill("a-genuinely-fine-password-1");
  await page.getByPlaceholder("Enter Age").fill("24");
  await page.getByRole("button", { name: /sign up|create account/i }).click();

  // Signup auto-logs-in and redirects to /dashboard (Signup.jsx).
  await expect(page.getByText("Dashboard", { exact: false }).first()).toBeVisible({ timeout: 10_000 });

  for (const { path, landmark } of PAGES) {
    await page.goto(path);
    await expect(page.getByText(landmark, { exact: false }).first()).toBeVisible({ timeout: 10_000 });

    const bodyText = await page.locator("body").innerText();
    for (const token of FORBIDDEN_TOKENS) {
      // Word-boundary match — "null" must not false-positive on e.g. "nullable"
      // in unrelated copy, though none is expected here.
      const re = new RegExp(`\\b${token}\\b`);
      expect(re.test(bodyText), `${path} rendered the literal token "${token}" for a zero-data user`).toBe(false);
    }
  }
});
