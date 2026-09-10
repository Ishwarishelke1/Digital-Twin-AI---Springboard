/**
 * src/components/SilkBackground.jsx
 *
 * Drop-in animated background for the auth pages' brand panel (Login/Signup/
 * ForgotPassword). Wraps React Bits' Silk component (Silk.jsx) so call sites
 * don't need to think about code-splitting or reduced-motion:
 *
 * - Silk pulls in `three` + `@react-three/fiber`, real weight this app
 *   otherwise doesn't carry (see ScenarioExplorer.jsx's Plotly chunk for the
 *   existing precedent of lazy-loading a heavy visualization dependency
 *   rather than letting it inflate the shared bundle). Lazy-loading it here
 *   keeps that cost off every route except the 3 auth pages.
 * - Skips mounting entirely under prefers-reduced-motion — this is a
 *   requestAnimationFrame-driven WebGL loop, so the CSS `motion-reduce:`
 *   variant used elsewhere in this app can't stop it; see
 *   usePrefersReducedMotion.js.
 *
 * Renders at reduced opacity over the panel's own gradient background so
 * that gradient still works as a visible fallback before the chunk loads,
 * on a slow connection, or if WebGL is unavailable.
 */
import { lazy, Suspense } from "react";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

const Silk = lazy(() => import("./Silk"));

export default function SilkBackground() {
  const prefersReducedMotion = usePrefersReducedMotion();

  if (prefersReducedMotion) return null;

  return (
    <div className="pointer-events-none absolute inset-0 opacity-60">
      <Suspense fallback={null}>
        <Silk speed={2.2} scale={1} noiseIntensity={1.2} />
      </Suspense>
    </div>
  );
}
