# Design system — "Field Notes"

> **Superseded.** This documents "Field Notes", the visual identity the app carried before the
> ground-up redesign. The app now runs on **"Studio"** — warm paper, Fraunces display serif, Inter
> body, JetBrains Mono for every figure — defined as design tokens in `frontend/src/index.css`.
> Kept for the reasoning it records about spacing, iconography and component states, much of which
> carried forward; its specific colour and type values did not. See [`SKILLS.md`](SKILLS.md) for the
> workflow the redesign went through.

This documents the visual design rules implemented across the app. It's a
companion to `CLAUDE.md` (which covers code conventions) — this file covers
*visual* rules: color, type, spacing, iconography, and where each lives in
code. Read this before adding a new screen or component so it matches
without needing a design review.

## Direction

The app was redesigned around one idea: **Digital Twin is a personal ledger
of your own growth, not enterprise SaaS software.** Concretely, that means
warm paper tones instead of cool slate, a serif for headings instead of an
all-sans hierarchy, small/quiet corner radii and hairline rules instead of
heavy rounding and drop shadows, and real content instead of decorative
emoji or filler stats.

Three low-fidelity directions were sketched and compared before committing
to this one — see the "Digital Twin Visual Directions" canvas from that
session if you want the rejected alternatives (a dark "Instrument Panel"
console look, and a cool "Blueprint Grid" schematic look).

## Where the system lives

Nearly the entire system is **token-level**, defined once in
`src/index.css`'s `@theme` block and `index.html`'s font `<link>`. Because
none of the shared `src/components/ui/*` primitives (`Card`, `Button`,
`Badge`, `StatTile`, `Modal`, `Drawer`, `Field`'s `Input`/`Select`/
`Textarea`, `Skeleton*`, `EmptyState`, `ProgressList`) hardcode a color,
radius, or shadow value — they all reference Tailwind's utility classes
(`bg-slate-50`, `rounded-2xl`, `shadow-sm`, etc.) — redefining the
underlying CSS custom properties re-themes the whole app without touching
component code. **Prefer extending the token set over hardcoding a new
value in a component.**

The one thing tokens can't reach is anything that takes a literal color
value instead of a class — chart libraries. Those pull from
`src/utils/chartColors.js`, which must be kept in sync with the palette
below by hand.

## Color

Defined as a full 50–900 ramp per family in `src/index.css`, overriding
Tailwind's own `slate`/`indigo`/`violet`/`emerald`/`amber`/`red` scales
(rather than inventing new class names — every `bg-indigo-600` in the app
keeps working, it just resolves to a different hex now). Every shade
actually used anywhere in the app is defined, including the `-100`/`-700`
tone shades `Badge` needs — a deliberate fix over the previous iteration,
which only overrode a handful of mid-scale shades and silently fell back to
Tailwind's cool default gray for everything else.

| Token | Hex | Role |
|---|---|---|
| `slate-50` | `#F6F1E7` | page background ("paper") |
| `slate-100` | `#EFE7D8` | secondary surface |
| `slate-200` | `#E4DACB` | borders |
| `slate-300` | `#CBBBA0` | strong borders |
| `slate-400` | `#A69A87` | placeholders, disabled |
| `slate-500` | `#8A7F72` | muted labels |
| `slate-600` | `#6E6355` | secondary text |
| `slate-700` | `#4A4033` | dark-mode surface/border |
| `slate-800` | `#2B2521` | primary text (light mode) / surface (dark mode) |
| `slate-900` | `#1C1712` | Sidebar background in dark mode; dark-mode base elsewhere |
| `indigo-100/600/700` | `#D3E6DF` / `#2F6F5E` / `#234F42` | **primary action accent** (teal) — buttons, links, active nav state |
| `violet-100/300/500/600/700` | … / `#8267C4` / … | **predicted-value accent** — reserved *only* for model/forecast output, never user-entered data (see "Predicted values" below) |
| `emerald-100/600/700` | … / `#1F7A52` / … | positive semantic (income, on-track, success) |
| `amber-100/600/700` | … / `#B5780F` / … | warning semantic |
| `red-100/600/700` | … / `#B23A34` / … | danger semantic (expense, destructive actions) |

**Dark mode** reuses this same ramp rather than defining a second palette —
it's driven by a `data-theme="dark"` attribute on `<html>` (a per-account
preference from `user.preferences.dark_mode`, applied in `AuthContext`, via
the `@custom-variant dark` in `index.css` — *not* the OS `prefers-color-scheme`
media query). Components reference `dark:bg-slate-800`, `dark:text-slate-100`,
etc., and because the ramp's light end is genuinely light and its dark end is
genuinely dark, the same tokens work as light-mode text/dark-mode surface or
vice versa without a second set of variables.

## Typography

Two paired families, loaded via Google Fonts `<link>` in `index.html`:

- `--font-serif`: **Source Serif 4** — every heading tag (`h1`–`h4`)
  app-wide, applied once in `index.css`'s `@layer base` so no component
  needs a `font-serif` class. Chosen as a deliberate pairing (both from
  Adobe's Source family, designed to work together) rather than reaching
  for an overused AI-generated-page default like Fraunces.
- `--font-sans`: **Source Sans 3** — body text, labels, buttons, everything
  else. (The previous system named "Inter" here but never actually loaded
  it as a webfont — it silently fell back to the OS system font. This is
  the first time a body face has actually been loaded.)

Numeric data (currency, scores, dates in tables) uses `font-mono` +
`tabular-nums` so columns of digits align — this predates the redesign and
is unchanged.

## Shape and elevation

Overridden once in `index.css`, cascades to every usage:

- `--radius-lg` / `--radius-xl`: `6px`
- `--radius-2xl`: `4px` (was `16px`) — this is the single biggest visual
  shift from the old "SaaS card" look to the current ledger/notebook look.
- `--shadow-sm` / `--shadow-md` / `--shadow-xl`: subtle, warm-tinted
  (`rgb(43 37 33 / …)` instead of Tailwind's neutral black-based defaults)
  — kept deliberately faint; most surfaces read as flat paper with a
  hairline `border`, not a floating card. `shadow-xl` is reserved for
  genuinely elevated, blocking UI (`Modal`, `Drawer`).

## Layout patterns

- **Cards** (`ui/Card.jsx`): white/dark surface, hairline border, small
  radius, faint shadow. The default container for any grouped content.
- **Tables**: header row gets a single `border-b`, no shaded background —
  a ledger rule, not an admin-table header band. Body rows get a bottom
  hairline between them and a subtle hover tint. See
  `TransactionTable.jsx` / `StudyTable.jsx` / `HabitTable.jsx` /
  `Activity.jsx` for the canonical pattern.
- **Lists as ledgers**: where a component would otherwise be a bordered
  box-per-row list (e.g. `SimulationHistoryList.jsx`), prefer a single
  container with `border-b` dividers between rows instead — reads as one
  continuous record rather than a stack of separate cards.
- **Progress bars**: always the custom div-based bar (`h-2.5
  rounded-full bg-slate-200`, inner `bg-indigo-600` sized by `%` via
  inline `style`) — never a native `<progress>` element, which can't be
  restyled consistently across browsers. `ui/ProgressList.jsx` is the
  shared version for a labeled list of bars; inline the same pattern
  directly (see `Dashboard.jsx`'s goal cards) when there's no shared list
  wrapper to reuse.

## Predicted values

Anything that is **model/forecast output rather than data the user
entered** — a projected savings figure, a simulation scenario's outcome,
next week's predicted study score — always carries the `violet` accent and,
where it's a standalone labeled value, a leading `✦` mark (see
`StatTile.jsx`, `PredictionCards.jsx`, `IncomeProjectionCard.jsx`,
`Dashboard.jsx`'s "AI Recommendation" card). This is the one deliberate,
consistent "icon" in the system — everything else is a real `lucide-react`
SVG icon or plain text (see below), but this mark exists specifically so a
predicted number is never visually mistaken for an actual one. Don't invent
a second way to signal "predicted" — reuse this.

## Iconography — no emoji

Every icon in the app is an inline SVG from `lucide-react` (already a
dependency, already used throughout `Sidebar`/`Navbar`-successor/chart
components). **Decorative emoji are not used anywhere in this codebase** —
an earlier pass through the app found and removed a wide pattern of emoji
used as faux-icons and copy decoration (chat avatars, quick-action tiles,
AI-insight string prefixes, page headings). If you're adding a new icon
need, reach for a `lucide-react` icon at `size={16–20}` and
`strokeWidth={1.8}` (the sizes/weight used everywhere else), not a Unicode
glyph. The sole exception is the `✦` predicted-value mark above, which is a
typographic marker, not a decorative icon.

## Chart colors

`src/utils/chartColors.js` exports the palette as plain hex strings for
Recharts `stroke`/`fill` props, which can't consume CSS custom properties.
Keep this file's values in sync with the `--color-*` tokens above by hand
whenever the palette changes — nothing enforces this automatically.

```js
CHART_COLORS = {
  action:    "#2F6F5E", // indigo-600 — primary series
  predicted: "#8267C4", // violet-500 — forecast/predicted series
  positive:  "#1F7A52", // emerald-600
  warning:   "#B5780F", // amber-600
  danger:    "#B23A34", // red-600
  grid:      "#E4DACB", // slate-200 — gridlines
  muted:     "#8A7F72", // slate-500 — secondary labels
}
```

## Navigation

The app has a single navigation surface: the **Sidebar**
(`components/Sidebar.jsx`), a fixed-left column (icon-only at `w-16` below
the `md` breakpoint, labeled at `w-64` from `md` up — same collapse pattern
throughout). There is no separate top navbar. Structure, top to bottom:

1. **Brand header** — logo mark + app name (hidden on the collapsed
   width).
2. **Nav groups** (`Overview` / `Track` / `Foresight`), each a labeled
   cluster of `NavLink`s — grouped by purpose, not flattened. There is no
   separate "You" group — identity lives in the profile dropdown below.
3. **AI Assistant** — visually separated below the groups with its own
   divider, since it's a preview feature, not a core section.
4. **Theme toggle** (bottom) — a sun/moon button that flips the saved
   `preferences.dark_mode` via `AuthContext`'s `toggleDarkMode` (same
   `PATCH /users/me/preferences` the old Settings checkbox used — dark
   mode is still a per-account, backend-persisted preference, just
   toggled from here now). Shows `Moon` in light mode ("switch to dark")
   and `Sun` in dark mode ("switch to light"). There is no notifications
   affordance — removed as unneeded rather than shipped as a disabled
   placeholder.
5. **Profile dropdown** (`ProfileMenu`, inside `Sidebar.jsx`) — avatar +
   name/role trigger (name hidden on the collapsed width) that opens a
   menu *upward* (`bottom-full`, since it's pinned to the bottom of the
   screen) containing My Profile, Settings, and Logout. Uses the same
   click-outside/Escape-to-close pattern as `Dashboard.jsx`'s
   `AddRecordMenu` — reuse that pattern for any future dropdown rather
   than inventing a new one.

A page-level top navbar existed earlier in the app (`components/Navbar.jsx`)
duplicating the greeting/avatar/settings/logout affordances already present
on `Dashboard.jsx`'s own header and now in the sidebar's profile block — it
was removed as redundant. `layouts/MainLayout.jsx` renders only `Sidebar` +
`<Outlet />` now. If a page needs a title, it renders its own `<h2>` (every
page does this already except `Habits.jsx`, a pre-existing gap unrelated to
this change).

## Adding to this system

- New color needs → add a shade to the existing family in `index.css`
  rather than reaching for an unthemed Tailwind color (`blue-500`,
  `sky-400`, etc.) — those resolve to Tailwind's stock palette and will
  visibly clash with everything else.
- New "elevated container" needs → use `Card`, not a hand-rolled
  `rounded-* border bg-white shadow-*` div.
- New chart → pull colors from `chartColors.js`, don't hardcode a hex.
- New icon need → `lucide-react`, never emoji.
- New predicted/forecast value → violet accent + `✦`, consistent with
  every other predicted value in the app.
