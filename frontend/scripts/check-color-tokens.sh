#!/usr/bin/env bash
# Fails if any Tailwind color class used in src/**/*.jsx references a shade that
# isn't defined in src/index.css's @theme block.
#
# Why this exists: Tailwind has no "undefined shade" error. An undefined rung
# silently resolves to Tailwind's own stock color, which is cool-toned and
# clashes with this project's warm "Studio" palette. The app shipped with 20 such
# shades — including focus:ring-indigo-500 on every input and border-red-500 on
# every form error — rendering in stock Tailwind rather than the design system.
# Nothing caught it because a grep for stale *hex values* passes cleanly; the
# defect is a missing definition, not a wrong one.
#
# Usage: ./scripts/check-color-tokens.sh   (run from frontend/)
set -euo pipefail

CSS="src/index.css"
SRC="src"
FAMILIES="slate|indigo|violet|emerald|amber|red"
PROPS="bg|text|border|border-t|border-b|border-l|border-r|ring|from|via|to|fill|stroke|divide|outline|accent|decoration|shadow"

used=$(grep -rhoE "(${PROPS})-(${FAMILIES})-[0-9]{2,3}" --include="*.jsx" "$SRC" \
  | sed -E "s/^(${PROPS})-//" | sort -u)

defined=$(grep -oE -- "--color-(${FAMILIES})-[0-9]{2,3}" "$CSS" \
  | sed 's/--color-//' | sort -u)

missing=$(comm -23 <(echo "$used") <(echo "$defined"))

if [ -n "$missing" ]; then
  echo "✗ Color shades used in JSX but NOT defined in $CSS @theme:"
  echo "$missing" | sed 's/^/    /'
  echo
  echo "  These silently fall through to stock Tailwind colors and will clash"
  echo "  with the Studio palette. Define them in $CSS, and contrast-verify each"
  echo "  in BOTH themes before committing (see REMEDIATION_PLAN.md)."
  exit 1
fi

echo "✓ All $(echo "$used" | wc -l | tr -d ' ') color shades used in JSX are defined in @theme."
