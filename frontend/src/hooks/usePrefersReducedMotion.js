/**
 * src/hooks/usePrefersReducedMotion.js
 *
 * Tracks the `(prefers-reduced-motion: reduce)` media query in JS. Most
 * motion in this app is pure CSS (Tailwind's `motion-reduce:` variant, see
 * index.css and Skeleton.jsx/Drawer.jsx), which the browser already disables
 * on its own — no JS needed there. This hook exists for the rarer case where
 * an effect can't be expressed as a CSS animation, e.g. a WebGL canvas driven
 * by a requestAnimationFrame loop (SilkBackground.jsx), where skipping the
 * work in JS also saves the GPU/battery cost, not just the visible motion.
 */
import { useState, useEffect } from "react";

export function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = (event) => setPrefersReducedMotion(event.matches);

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  return prefersReducedMotion;
}
