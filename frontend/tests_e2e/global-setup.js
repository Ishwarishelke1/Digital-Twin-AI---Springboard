// tests_e2e/global-setup.js — logs in ONCE via a real request (no browser
// needed for this) and saves the resulting httpOnly cookie as storageState,
// reused by every spec in both projects. `/auth/login` is rate-limited
// (10/minute) — logging in once here rather than per-spec is what keeps a
// 13-page, 2-theme run under that limit.
import { request } from "@playwright/test";

const EMAIL = "playwright-demo@example.com";
const PASSWORD = "a-genuinely-fine-password-1";

export default async function globalSetup() {
  const ctx = await request.newContext({ baseURL: "http://localhost:5173" });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { email: EMAIL, password: PASSWORD },
  });
  if (!res.ok()) {
    throw new Error(
      `Playwright global setup: login failed (${res.status()}). Is the backend running ` +
      `against the seeded database? See tests_e2e/README.md. Body: ${await res.text()}`
    );
  }
  await ctx.storageState({ path: "tests_e2e/.auth/user.json" });
  await ctx.dispose();
}
