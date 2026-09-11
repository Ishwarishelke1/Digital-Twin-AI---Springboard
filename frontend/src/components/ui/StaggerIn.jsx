/**
 * src/components/ui/StaggerIn.jsx
 *
 * Per-item mount animation for short, card-shaped lists (a handful of items,
 * not a table with unbounded rows) — items fade/scale in one after another
 * instead of all appearing at once. Inspired by React Bits' "AnimatedList",
 * but built from scratch against this app's own motion spec rather than
 * importing that component: it ships hardcoded dark (#111/#222) colors and
 * its own scrollbar chrome that would clash with this app's Tailwind-token
 * light/dark theming, and it renders its own list items rather than wrapping
 * arbitrary children.
 *
 * The opacity/scale values and 160ms/ease-out timing intentionally match
 * index.css's existing `modal-in` keyframe — one deliberate motion feel
 * reused, not a second one invented.
 */
import { motion } from "motion/react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

const STAGGER_STEP = 0.06;
const MAX_DELAY = 0.42;

export default function StaggerIn({ index = 0, className, children }) {
  const prefersReducedMotion = usePrefersReducedMotion();

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{
        duration: 0.16,
        ease: "easeOut",
        delay: Math.min(index * STAGGER_STEP, MAX_DELAY),
      }}
    >
      {children}
    </motion.div>
  );
}
