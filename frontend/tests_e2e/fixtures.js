// tests_e2e/fixtures.js — the two things every spec in this suite needs:
// noise detection, and theme control.
import { test as base, expect } from "@playwright/test";

/**
 * Extends Playwright's `test` with:
 *
 *  - `page` that fails the test if anything logs a console error, an
 *    uncaught exception, or a response >= 400 happens during it — the single
 *    most valuable piece of this suite. Most of this project's real defects
 *    (sign-up unreachable by direct URL, undefined colour tokens, an empty
 *    Groq reply) announced themselves in exactly this band and nowhere else;
 *    a page that renders while throwing looks identical to a clean one
 *    without this. ALLOWED_NOISE is the one documented exception: the
 *    session probe's 401 on a route it doesn't expect a session on is a
 *    valid answer, not an error.
 *
 *  - `setTheme(dark)` — flips the account's dark_mode preference server-side
 *    (PATCH /users/me/preferences) and reloads. Playwright's `colorScheme`
 *    emulation does nothing here: this app's dark mode is driven by
 *    AuthContext writing `documentElement.dataset.theme` from
 *    `user.preferences.dark_mode`, not `prefers-color-scheme` — confirmed by
 *    reading frontend/src/context/AuthContext.jsx and index.css's
 *    `@custom-variant dark` before writing this, not assumed.
 */
const ALLOWED_NOISE = [
  /\/api\/v1\/users\/me.*401/, // the session probe on a public route — a valid answer, not an error
];

function isAllowed(text) {
  return ALLOWED_NOISE.some((re) => re.test(text));
}

// Chrome's own "Failed to load resource: the server responded with a status
// of NNN" console.error carries no URL in its text — only the associated
// network response object has that, which page.on("response") below already
// evaluates against ALLOWED_NOISE with the real URL. Without this, the exact
// same allow-listed 401 gets flagged twice: correctly ignored at the network
// level, then flagged anyway by this redundant, URL-blind echo of it.
const GENERIC_RESOURCE_LOAD_FAILURE = /^Failed to load resource: the server responded with a status of \d+/;

export const test = base.extend({
  page: async ({ page }, use) => {
    const violations = [];

    page.on("console", (msg) => {
      if (
        msg.type() === "error" &&
        !isAllowed(msg.text()) &&
        !GENERIC_RESOURCE_LOAD_FAILURE.test(msg.text())
      ) {
        violations.push(`console.error: ${msg.text()}`);
      }
    });
    page.on("pageerror", (err) => {
      violations.push(`uncaught exception: ${err.message}`);
    });
    page.on("response", (res) => {
      const url = res.url();
      if (res.status() >= 400 && !isAllowed(`${url} ${res.status()}`) && url.includes("/api/")) {
        violations.push(`${res.status()} ${res.request().method()} ${url}`);
      }
    });

    await use(page);

    expect(violations, `console/network noise during this test:\n${violations.join("\n")}`).toEqual([]);
  },

  setTheme: async ({ page, request }, use) => {
    await use(async (dark) => {
      const res = await request.patch("http://localhost:5173/api/v1/users/me/preferences", {
        data: { dark_mode: dark },
      });
      if (!res.ok()) throw new Error(`setTheme(${dark}) failed: ${res.status()}`);
      await page.reload();
    });
  },
});

export { expect };
